import datetime
import json
import socket
socket.setdefaulttimeout(15)
import requests
import re
import threading
import time
import urllib.parse
import urllib.request

from apscheduler.triggers.cron import CronTrigger
from app.plugins import _PluginBase
from app.sdk.logging import logger
try:
    from app.schemas.types import NotificationType
except Exception:
    NotificationType = None

class MetaFiller(_PluginBase):
    """缺失剧集元数据补全工具：扫描 Emby 缺标题/简介的剧集，从电视猫抓取补全。"""

    plugin_name = "缺失剧集元数据补全（自用）"
    plugin_desc = "定时扫描 Emby 媒体库，找出缺失标题/简介的剧集，从电视猫抓取补全。"
    plugin_icon = "Emby_A.png"
    plugin_color = "#098663"
    plugin_version = "1.2.0"
    plugin_author = "asice999"
    author_url = "https://github.com/asice999"
    plugin_config_prefix = "MetaFiller_"

    _enabled = False
    _conf = {}
    _cron = "0 3 * * *"
    _onlyonce = False
    _emby_url = ""
    _emby_key = ""
    _fill_title = True
    _fill_desc = True
    _max_series = 0
    _overwrite = False
    _fill_image = True
    _notify = True
    _prefer_cn_source = False
    _only_series = ""
    _timeout = 15

    _report = {"last": "", "ok": 0, "fail": 0, "img": 0, "log": [], "skipped": []}
    _event = threading.Event()
    _UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"
    def init_plugin(self, config=None):
        self._conf = config or {}
        self._enabled = bool(config.get("enabled")) if config else False
        self._cron = config.get("cron") or "0 3 * * *"
        self._onlyonce = bool(config.get("onlyonce")) if config else False
        saved = self.get_data("creds") or {}
        self._emby_url = (config.get("emby_url") or saved.get("url") or "").strip().rstrip("/")
        self._emby_key = (config.get("emby_key") or saved.get("key") or "").strip()
        if self._emby_url and self._emby_key:
            if saved.get("url") != self._emby_url or saved.get("key") != self._emby_key:
                self.save_data("creds", {"url": self._emby_url, "key": self._emby_key})
            self._conf["emby_url"] = self._emby_url
            self._conf["emby_key"] = self._emby_key
        self._fill_title = bool(config.get("fill_title", True))
        self._fill_desc = bool(config.get("fill_desc", True))
        max_series = int(config.get("max_series") or 0)
        self._max_series = max_series if max_series > 0 else 0
        self._scan_scope = config.get("scan_scope") or "all"
        self._overwrite = bool(config.get("overwrite", False))
        self._fill_image = bool(config.get("fill_image", True))
        self._notify = bool(config.get("notify", True))
        self._prefer_cn_source = bool(config.get("prefer_cn_source", False))
        self._only_series = (config.get("only_series") or "").strip()
        if self._onlyonce:
            self._onlyonce = False
            self.update_config({**self._conf, "onlyonce": False})
            threading.Thread(target=self._run_once, daemon=True).start()
    def get_state(self):
        return self._enabled
    def get_service(self):
        if not self._enabled:
            return []
        return [{
            "id": "MetaFillerScan",
            "name": "缺失元数据扫描",
            "trigger": CronTrigger.from_crontab(self._cron),
            "func": self.__scan_and_fill,
            "kwargs": {},
        }]
    def get_form(self):
        return [
            {"component": "VRow", "content": [
                {"component": "VCol", "props": {"cols": 6}, "content": [
                    {"component": "VSwitch", "props": {
                        "model": "enabled", "label": "启用插件"}}]},
                {"component": "VCol", "props": {"cols": 6}, "content": [
                    {"component": "VSwitch", "props": {
                        "model": "onlyonce", "label": "立即运行一次"}}]},
            ]},
            {"component": "VRow", "content": [
                {"component": "VCol", "props": {"cols": 12}, "content": [
                    {"component": "VCronField", "props": {
                        "model": "cron", "label": "扫描周期"}}]},
            ]},
            {"component": "VRow", "content": [
                {"component": "VCol", "props": {"cols": 6}, "content": [
                    {"component": "VTextField", "props": {
                        "model": "emby_url", "label": "Emby 地址",
                        "placeholder": "留空自动从系统配置读取"}}]},
                {"component": "VCol", "props": {"cols": 6}, "content": [
                    {"component": "VTextField", "props": {
                        "model": "emby_key", "label": "Emby API Key",
                        "placeholder": "留空自动从系统配置读取"}}]},
            ]},
            {"component": "VRow", "content": [
                {"component": "VCol", "props": {"cols": 4}, "content": [
                    {"component": "VSwitch", "props": {
                        "model": "fill_title", "label": "补标题"}}]},
                {"component": "VCol", "props": {"cols": 4}, "content": [
                    {"component": "VSwitch", "props": {
                        "model": "fill_desc", "label": "补简介"}}]},
                {"component": "VCol", "props": {"cols": 4}, "content": [
                    {"component": "VTextField", "props": {
                        "model": "max_series", "label": "每次扫描剧数上限",
                        "type": "number", "placeholder": "0=全部"}}]},
            ]},
            {"component": "VRow", "content": [
                {"component": "VCol", "props": {"cols": 12}, "content": [
                    {"component": "VSelect", "props": {
                        "model": "scan_scope", "label": "扫描范围",
                        "items": [
                            {"title": "全部媒体库", "value": "all"},
                            {"title": "国产剧", "value": "国产剧"},
                            {"title": "国漫", "value": "国漫"},
                            {"title": "综艺", "value": "综艺"},
                            {"title": "纪录片", "value": "纪录片"},
                            {"title": "儿童", "value": "儿童"},
                            {"title": "欧美剧", "value": "欧美剧"},
                            {"title": "日韩剧", "value": "日韩剧"},
                        ]}}]},
            ]},
            {"component": "VRow", "content": [
                {"component": "VCol", "props": {"cols": 4}, "content": [
                    {"component": "VSwitch", "props": {
                        "model": "overwrite", "label": "覆盖已有数据（关闭时只补缺失）",
                        "hint": "开启后会用数据源内容替换已有标题/简介"}}]},
                {"component": "VCol", "props": {"cols": 4}, "content": [
                    {"component": "VSwitch", "props": {
                        "model": "fill_image", "label": "补分集缩略图"}}]},
                {"component": "VCol", "props": {"cols": 4}, "content": [
                    {"component": "VSwitch", "props": {
                        "model": "notify", "label": "完成后发送通知"}}]},
            ]},
            {"component": "VRow", "content": [
                {"component": "VCol", "props": {"cols": 4}, "content": [
                    {"component": "VSwitch", "props": {
                        "model": "dry_run", "label": "仅分析不写入（预览）",
                        "hint": "只统计待补数量与冲突，不修改 Emby"}}]},
                {"component": "VCol", "props": {"cols": 4}, "content": [
                    {"component": "VSwitch", "props": {
                        "model": "prefer_cn_source", "label": "中文源优先（电视猫优先）",
                        "hint": "开启后优先用电视猫补中文简介"}}]},
            ]},
        ], self._conf
    def get_page(self):
        return {
            "component": "div",
            "content": [
                {"component": "VRow", "content": [
                    {"component": "VCol", "props": {"cols": 12}, "content": [
                        {"component": "VCard", "props": {"variant": "tonal"},
                         "content": [
                            {"component": "VCardText", "text": "上次运行: %s" % self._report.get("last", "从未")},
                            {"component": "VCardText", "text": "成功: %d, 失败: %d" % (
                                self._report.get("ok", 0), self._report.get("fail", 0))},
                            {"component": "VCardText", "content": [
                                {"component": "VTextarea", "props": {
                                    "model": "report", "readonly": True,
                                    "rows": 12, "variant": "monospace"}}
                            ]},
                            {"component": "VCardText", "text": "丢弃项: %d" % len(self._report.get("skipped", []))},
                            {"component": "VCardText", "text": "丢弃分类: %s" % (", ".join([f"%s:%s" % (k, v) for k, v in (self._report.get("skip_kinds") or {}).items()]) or "无")},
                            {"component": "VCardText", "text": "本轮模式: %s | 范围: %s" % (
                                "预览(不写入)" if self._report.get("dry_run") else "写入",
                                self._report.get("scope", "all"))},
                            {"component": "VCardText", "text": "待补统计 标题:%d 简介:%d 图片:%d" % (
                                (self._report.get("pending") or {}).get("title", 0),
                                (self._report.get("pending") or {}).get("desc", 0),
                                (self._report.get("pending") or {}).get("image", 0))},
                            {"component": "VCardText", "text": "历史(最近%d次): %s" % (
                                len(self._report.get("history") or []),
                                " | ".join([
                                    "%s ok%s/fail%s/img%s%s" % (h.get("ts", "")[5:16], h.get("ok", 0),
                                                                h.get("fail", 0), h.get("img", 0),
                                                                "(预览)" if h.get("dry_run") else "")
                                    for h in (self._report.get("history") or [])[-5:]]) or "无")},
                        ]}
                    ]},
                ]},
            ]
        }
    def get_api(self):
        return [{
            "path": "/metafiller/report",
            "endpoint": self.__api_report,
            "methods": ["GET"],
            "summary": "补全报告",
        }]
    def __api_report(self, *args, **kwargs):
        return json.dumps(self._report, ensure_ascii=False)
    def _run_once(self):
        time.sleep(2)
        try:
            self.__scan_and_fill()
        except Exception as e:
            logger.info(f"运行异常: {e}")
            self.save_data("report", self._report)
        self.__notify_done()
    def __scan_and_fill(self):
        if not self._enabled:
            return
        start = time.time()
        hist = self.get_data("history") or []
        self._report = {"last": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "ok": 0, "fail": 0, "img": 0, "log": [], "skipped": [],
                        "dry_run": self._dry_run, "scope": (self._scan_scope or "all"),
                        "pending": {"title": 0, "desc": 0, "image": 0},
                        "history": hist[-9:]}
        base = self._emby_url
        key = self._emby_key
        if not base or not key:
            logger.info("Emby 地址或 API Key 未配置")
            self.save_data("report", self._report)
            return
        scope = (self._scan_scope or "all").strip()
        path_prefix = {
            "国产剧": "/media/Video/电视剧/国产剧/",
            "国漫": "/media/Video/电视剧/国漫/",
            "综艺": "/media/Video/电视剧/综艺/",
            "纪录片": "/media/Video/电视剧/纪录片/",
            "儿童": "/media/Video/电视剧/儿童/",
            "欧美剧": "/media/Video/电视剧/欧美剧/",
            "日韩剧": "/media/Video/电视剧/日韩剧/",
        }.get(scope, "")
        fetch_limit = str(self._max_series * 10 if self._max_series and self._max_series > 0 else 1000)
        if path_prefix:
            series = self.__emby_get(base, key, "/Items", {
                "IncludeItemTypes": "Series", "Recursive": "true",
                "Limit": fetch_limit, "Fields": "ProductionYear,Path"})
            items = [x for x in ((series or {}).get("Items") or []) if (x.get("Path") or "").startswith(path_prefix)]
        else:
            series = self.__emby_get(base, key, "/Items", {
                "IncludeItemTypes": "Series", "Recursive": "true",
                "Limit": fetch_limit, "Fields": "ProductionYear"})
            items = (series or {}).get("Items") or []
        if self._only_series:
            items = [x for x in items if self.__series_selected(x.get("Id") or "", x.get("Name") or "")]
        limit = int(self._max_series or 0)
        logger.info(f"扫描范围[{scope}]，扫描到 {len(items)} 部剧，逐个检查缺失…")
        if limit <= 0:
            limit = len(items)
        processed = 0
        fail_series = []
        done = set(self.get_data("cursor") or [])
        if done:
            logger.info(f"检测到上轮未完成，已处理 {len(done)} 部，续跑剩余")
        for s in items:
            if processed >= limit:
                break
            sid = s.get("Id")
            name = s.get("Name") or ""
            if not sid:
                continue
            if sid in done:
                continue
            time.sleep(2.5)
            ok = False
            try:
                filled = self.__fill_series(base, key, sid, name, s.get("ProductionYear"))
                ok = (filled >= 0 and filled != -1)
            except Exception as e:
                filled = 0
                logger.info(f"[{name}] 异常: {e}")
            if filled > 0:
                processed += 1
                self._report["ok"] += filled
                logger.info(f"[{name}] 补全 {filled} 集")
            elif filled == -1:
                self._report["fail"] += 1
                fail_series.append(name)
                logger.info(f"[{name}] 电视猫未找到，跳过")
            if ok:
                done.add(sid)
                self.save_data("cursor", list(done))
        self._report["series"] = self._report.get("series", [])
        if fail_series:
            self._report["log"].append(f"未找到剧: {', '.join(fail_series[:10])}")
        self._report["pending"] = self._report.get("pending", {"title":0,"desc":0,"image":0})
        self._report["log"].append(f"总耗时 {int(time.time()-start)}s")
        hist = self.get_data("history") or []
        hist.append({"ts": self._report["last"], "ok": self._report["ok"], "fail": self._report["fail"],
                     "img": self._report["img"], "skip": len(self._report["skipped"]),
                     "dry_run": self._report.get("dry_run", False)})
        self.save_data("history", hist[-10:])
        self.save_data("report", self._report)
        if len(done) >= len([x for x in items if x.get('Id')]):
            self.save_data("cursor", [])   # 正常跑完清断点
    def __fill_series(self, base, key, sid, name, year=None):
        logger.info(f"开始处理 [{name}] (年:{year})")
        eps = self.__emby_get(base, key, f"/Shows/{sid}/Episodes", {"Fields": "Name,Overview,ParentIndexNumber"})
        items = (eps or {}).get("Items") or []
        # find missing episodes
        missing = []
        for ep in items:
            n = ep.get("IndexNumber") or 0
            en = (ep.get("Name") or "").strip()
            ov = (ep.get("Overview") or "").strip()
            if self._overwrite:
                need_title = self._fill_title
                need_desc = self._fill_desc
            else:
                need_title = self._fill_title and (not en or self.__is_placeholder(en, n))
                need_desc = self._fill_desc and not self.__ov_or_placeholder(ov)
            if need_title or need_desc:
                sn = ep.get("ParentIndexNumber")
                if need_title:
                    self._report["pending"]["title"] = self._report["pending"].get("title", 0) + 1
                if need_desc:
                    self._report["pending"]["desc"] = self._report["pending"].get("desc", 0) + 1
                missing.append((n, ep.get("Id"), en, need_title, need_desc,
                                sn if sn is not None else 1))
        if not missing:
            logger.info(f"[{name}] 无缺失（{len(items)} 集完整），跳过")
            return 0
        mode = "覆盖模式" if self._overwrite else "补缺模式"
        logger.info(f"[{name}] {mode}：待处理 {len(missing)}/{len(items)} 集，开始抓取")
        # 豆瓣条目校验（仅验证，不写入）
        self.__douban_match(name, year)
        # 按季分组，每季独立抓取（多季剧不能共用一套数据）
        seasons = sorted({m[5] for m in missing})
        real_seasons = {sn for sn in seasons if sn > 0}
        multi_season = len(real_seasons) > 1
        logger.info(f"[{name}] 涉及 {len(seasons)} 季: {seasons}，多季保护:{multi_season}")
        tid_cached = self.__tmdb_search(name, year)
        data_by_season = {}
        img_by_season = {}
        seasonless_by_season = {}
        for sn in seasons:
            sdata = self.__tmdb_fetch_all(name, year, sn, tid_cached) or {}
            seasonless = False
            if sdata:
                logger.info(f"[{name}] S{sn} TMDB 命中 {len(sdata)} 集")
            if not sdata:
                if sn == 0 or multi_season:
                    # TVDB/Emby 是主源；无季号源无法可靠映射到多季剧，宁缺勿错
                    logger.info(f"[{name}] S{sn} TMDB 未命中，多季/特别篇跳过无季号回退")
                    self.__skip(name, sn, "tmdb_no_season", "多季/特别篇，无季号源不参与")
                if self._prefer_cn_source:
                    logger.info(f"[{name}] S{sn} 中文源优先，回退电视猫/央视/TMDB")
                    code = self.__tvmao_search(name, year)
                    if code:
                        sdata = self.__tvmao_fetch_all(code) or {}
                        seasonless = bool(sdata)
                        if sdata:
                            logger.info(f"[{name}] S{sn} 电视猫命中 {len(sdata)} 集")
                    if not sdata:
                        sdata = self.__cctv_fetch_all(name) or {}
                        seasonless = bool(sdata)
                        if sdata:
                            logger.info(f"[{name}] S{sn} 央视网命中 {len(sdata)} 集")
                    if not sdata:
                        sdata = self.__tmdb_fetch_all(name, year, sn, tid_cached) or {}
                        seasonless = bool(sdata)
                        if sdata:
                            logger.info(f"[{name}] S{sn} TMDB 兜底命中 {len(sdata)} 集")
                else:
                    logger.info(f"[{name}] S{sn} TMDB 未命中，回退电视猫/央视")
                    code = self.__tvmao_search(name, year)
                    if code:
                        sdata = self.__tvmao_fetch_all(code) or {}
                        seasonless = bool(sdata)
                        if sdata:
                            logger.info(f"[{name}] S{sn} 电视猫命中 {len(sdata)} 集")
                    if not sdata:
                        sdata = self.__cctv_fetch_all(name) or {}
                        seasonless = bool(sdata)
                        if sdata:
                            logger.info(f"[{name}] S{sn} 央视网命中 {len(sdata)} 集")
            if not sdata:
                logger.info(f"[{name}] S{sn} 全源未命中")
                self.__skip(name, sn, "no_source", "全源未命中")
            data_by_season[sn] = sdata
            img_by_season[sn] = self.__tmdb_fetch_images(tid_cached, sn) if (sdata and tid_cached) else {}
            seasonless_by_season[sn] = seasonless
        if not any(data_by_season.values()):
            logger.info(f"[{name}] 全源未命中")
            return 0
        filled = 0
        uid = self.__get_uid(base, key)
        if not uid:
            logger.info(f"[{name}] 无法获取 Emby 用户")
            return 0
        # 集数一致性校验：TMDB 季集数远少于库内该季集数，说明季体系不一致，弃用
        for sn in list(data_by_season.keys()):
            if seasonless_by_season.get(sn) or not data_by_season.get(sn):
                continue
            lib_max = max([ep.get("IndexNumber") or 0 for ep in items
                           if (ep.get("ParentIndexNumber") if ep.get("ParentIndexNumber") is not None else 1) == sn] or [0])
            src_max = max(data_by_season[sn].keys())
            if lib_max and src_max and src_max * 2 < lib_max:
                logger.info(f"[{name}] S{sn} 源集数({src_max})远少于库内({lib_max})，季体系不符，弃用")
                self.__skip(name, sn, "source_too_short", f"源{src_max}集 < 库内{lib_max}集")
                data_by_season[sn] = {}
        if not any(data_by_season.values()):
            logger.info(f"[{name}] 校验后无可用数据")
            return 0
        for n, eid, cur_name, need_title, need_desc, sn in missing:
            season_data = data_by_season.get(sn) or {}
            # seasonless 仅允许单季剧；多季保护下永不跨季猜集号
            td = season_data.get(n) if not seasonless_by_season.get(sn) else None
            if seasonless_by_season.get(sn) and not multi_season and sn == 1:
                td = season_data.get(n)
            if not td:
                continue
            title, desc = td
            if not need_title and not need_desc:
                continue
            item = self.__emby_get(base, key, f"/Users/{uid}/Items/{eid}")
            if not item:
                continue
            changed = False
            if need_title and title and title != cur_name:
                item["Name"] = title
                changed = True
            if need_desc and desc:
                item["Overview"] = desc
                changed = True
            if changed and not self._dry_run:
                code = self.__emby_post(base, key, f"/Items/{eid}", item)
                if code == 204:
                    filled += 1
                time.sleep(0.3)
            elif changed and self._dry_run:
                filled += 1
            if self._fill_image:
                img = (img_by_season.get(sn) or {}).get(n)
                if img and not (item.get("ImageTags") or {}).get("Primary"):
                    self._report["pending"]["image"] = self._report["pending"].get("image", 0) + 1
                    if not self._dry_run:
                        st = self.__emby_upload_image(base, key, eid, img, "Primary")
                        if st in (200, 204):
                            self._report["img"] = self._report.get("img", 0) + 1
                        time.sleep(0.3)
        return filled
    @staticmethod
    def __ov_or_placeholder(text):
        t = (text or '').strip()
        return (not t) or t.startswith('暂无英文版的简介') or t.startswith('暂无简介')


    def __tvmao_search(self, name, year=None):
        """Bing site 搜索定位电视猫剧集 code，带剧名+年份双重校验（年份软过滤）"""
        q = urllib.parse.quote(f"site:tvmao.com {name}")
        try:
            resp = requests.get(f"https://cn.bing.com/search?q={q}",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"},
                timeout=10)
            html = resp.text
        except Exception as e:
            logger.info(f"Bing 搜索失败: {e}")
            return None
        codes = re.findall(r'https?://(?:www|m)\.tvmao\.com/(kanju|drama)/([A-Za-z0-9_-]{6,})', html)
        if not codes:
            return None
        from collections import Counter
        kanju = [c for t, c in codes if t == "kanju"]
        pool = kanju or [c for t, c in codes]
        if not pool:
            return None
        ordered = [c for c, _ in Counter(pool).most_common(6)]
        fallback = None
        for code in ordered:
            try:
                home = self.__tvmao_get(f"https://www.tvmao.com/kanju/{code}")
                if not home:
                    home = self.__tvmao_get(f"https://www.tvmao.com/drama/{code}")
                if not home:
                    continue
                t = re.search(r"<title>([^<]{0,60})", home)
                page_title = t.group(1).strip() if t else ""
                if name not in page_title:
                    continue
                if year:
                    years = self.__extract_years(home)
                    if year in years:
                        return code
                if fallback is None:
                    fallback = code
            except Exception:
                continue
        return fallback

    @staticmethod
    def __extract_years(html):
        """从剧集主页提取年份集合：首播日期附近优先，全页 20xx 兜底"""
        years = set()
        m = re.search(r"首播[：:]\s*(\d{4})", html)
        if m:
            years.add(int(m.group(1)))
        for y in re.findall(r"(\d{4})-(\d{2})-(\d{2})", html):
            years.add(int(y[0]))
        for y in re.findall(r"(\d{4})年", html):
            years.add(int(y[0]))
        return years

    @staticmethod
    def __tvmao_get(url):
        """GET 电视猫页面，Chrome UA"""
        try:
            resp = requests.get(url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"},
                timeout=10)
            return resp.text
        except Exception:
            return None
    def __tvmao_fetch_all(self, code):
        """抓取全部剧集标题+简介，返回 {n: (title, desc)}"""
        import urllib.request
        result = {}
        n = 1
        max_eps = 400  # ponytail: 先覆盖长篇到400集；更长再提参数
        fail_count = 0
        while n <= max_eps:
            p = (n - 1) // 3
            url = f"https://m.tvmao.com/kanju/{code}/episode/{p}-{n}"
            logger.info(f"  TVMAO: 第{n}集…")
            try:
                resp = requests.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"}, timeout=6)
                html = resp.text
            except Exception:
                fail_count += 1
                if fail_count >= 3:
                    break
                n += 1
                continue
            fail_count = 0
            import html as _h
            # 标题：<p> 里的「第N集：标题」
            title = None
            for p_text in re.findall(r'<p[^>]*>(.*?)</p>', html, re.S):
                text = re.sub(r'<[^>]+>', '', p_text).strip()
                m = re.match(r'第(\d+)集[：:]\s*(.+)', text)
                if m and int(m.group(1)) == n and len(m.group(2)) <= 40:
                    title = m.group(2).strip()
                    break
            # 简介：meta description 纯净正文（不含评论/推荐/广告）
            desc = ""
            md = re.search(r'<meta\s+name="description"\s+content="(.*?)"\s*/?>', html, re.S)
            if md:
                d = _h.unescape(md.group(1)).strip()
                d = re.sub(r'^第\d+集[：:]\s*', '', d)
                d = re.sub(r'\.{3,}$|…+$', '', d).strip()
                if len(d) >= 20:
                    desc = d
            if title or desc:
                result[n] = (title or "", desc)
                n += 1
            else:
                break
            time.sleep(0.5)
        return result
    def __douban_match(self, name, year=None):
        """豆瓣条目校验：仅返回匹配的 subject id，不参与分集正文写入"""
        try:
            url = "https://movie.douban.com/j/subject_suggest"
            r = requests.get(url, params={"q": name}, headers={"User-Agent": self._UA}, timeout=10)
            arr = r.json() if r.text else []
        except Exception as e:
            logger.info(f"豆瓣校验失败: {e}")
            return None
        for it in arr or []:
            if (it.get("title") or "").strip() == name and (not year or str(it.get("year") or "") == str(year)):
                logger.info(f"[{name}] 豆瓣命中 subject={it.get('id')} episode={it.get('episode')}")
                return str(it.get("id"))
        for it in arr or []:
            if (it.get("title") or "").strip() == name:
                logger.info(f"[{name}] 豆瓣命中 subject={it.get('id')} episode={it.get('episode')}")
                return str(it.get("id"))
        return None

    @staticmethod
    def __norm_name(text):
        return re.sub(r'[\s·•:：,，.!！?？()（）\[\]【】\'\"]+', '', (text or '')).strip().lower()

    def __tmdb_search(self, name, year=None):
        """带缓存的 TMDB 搜索，整部剧只真正搜一次"""
        ck = f"{name}|{year}"
        if not hasattr(self, "_tid_cache"):
            self._tid_cache = {}
        if ck not in self._tid_cache:
            self._tid_cache[ck] = self.__tmdb_search_raw(name, year)
        return self._tid_cache[ck]

    def __tmdb_search_raw(self, name, year=None):
        """TMDB 网页搜索剧集 id，中文名优先，年份优先匹配"""
        try:
            url = "https://www.themoviedb.org/search/tv?query=" + urllib.parse.quote(name) + "&language=zh-CN"
            html_text = requests.get(url, headers={"User-Agent": self._UA}, timeout=10).text
        except Exception as e:
            logger.info(f"TMDB 搜索失败: {e}")
            return None
        target = self.__norm_name(name)
        cards = re.findall(r'/tv/(\d+)[^"]*"[^>]*>\s*<h2[^>]*>([^<]{1,60})</h2>.*?(\d{4})',
                           html_text, re.S)
        if cards:
            for tid, title, y in cards:
                tt = self.__norm_name(title)
                if tt == target and (not year or int(y) == year):
                    return tid
            for tid, title, y in cards:
                tt = self.__norm_name(title)
                if tt == target or target in tt or tt in target:
                    if not year or int(y) == year:
                        return tid
            for tid, title, y in cards:
                tt = self.__norm_name(title)
                if tt == target or target in tt or tt in target:
                    return tid
        m = re.search(r'/tv/(\d+)', html_text)
        return m.group(1) if m else None

    def __tmdb_fetch_all(self, name, year=None, season=1, tid=None):
        """从 TMDB 中文季页面抓 {n: (title, desc)}"""
        tid = tid or self.__tmdb_search(name, year)
        if not tid:
            return {}
        try:
            url = f"https://www.themoviedb.org/tv/{tid}/season/{season}?language=zh-CN"
            resp = requests.get(url, headers={"User-Agent": self._UA}, timeout=15)
            page = resp.text
            if resp.status_code != 200 or "Page Not Found" in page[:4000]:
                logger.info(f"[{name}] TMDB 无 S{season} 季页面(tv/{tid})")
                return {}
            # 校验页面确属该季，避免解析到其它季内容
            og = re.search(r'property="og:title" content="([^"]*)"', page)
            if og:
                mseq = re.search(r'(\d+)', og.group(1))
                if mseq and int(mseq.group(1)) != int(season):
                    logger.info(f"[{name}] TMDB S{season} 页面季号不符({og.group(1)})，丢弃")
                    return {}
        except Exception as e:
            logger.info(f"TMDB 季页面失败: {e}")
            return {}
        result = {}
        import html as _html
        starts = [m.start() for m in re.finditer(r'<div class="card"[^>]*data-url="[^\"]*?/episode/\d+', page)]
        starts.append(len(page))
        for i in range(len(starts) - 1):
            blk = page[starts[i]:starts[i + 1]]
            mn = re.search(r'data-url="[^"]*/episode/(\d+)[^"]*"', blk)
            if not mn:
                continue
            n = int(mn.group(1))
            mt = (re.search(r'<div class="episode_title">\s*<h3><a[^>]*title="[^"]*Episode\s+\d+\s+-\s+([^"]+)"', blk, re.S)
                  or re.search(r'<div class="episode_title">\s*<h3><a[^>]*>(.*?)</a>', blk, re.S)
                  or re.search(r'title="[^"]*Episode\s+\d+\s+-\s+([^"]+)"', blk))
            mo = re.search(r'<div class="overview">\s*<p>(.*?)</p>', blk, re.S)
            title = _html.unescape(re.sub(r'<[^>]+>', '', mt.group(1))).strip() if mt else ""
            desc = _html.unescape(re.sub(r'<[^>]+>', '', mo.group(1))).strip() if mo else ""
            if title or desc:
                result[n] = (title, desc)
        if result:
            logger.info(f"[{name}] TMDB 命中 {len(result)} 集 (tv/{tid} S{season})")
        return result

    def __cctv_fetch_all(self, name):
        """央视网搜索接口，适合央视综艺/纪录片。用 DRETITLE 里的期号/集号匹配"""
        import html as _h
        try:
            r = requests.get("https://search.cctv.com/m/if3g_search.php",
                params={"page": 1, "qtext": name, "type": "video",
                        "sort": "SCORE", "pageSize": 60, "channel": ""},
                headers={"User-Agent": self._UA}, timeout=12)
            data = r.json()
        except Exception as e:
            logger.info(f"央视搜索失败: {e}")
            return {}
        result = {}
        for it in (data.get("list") or []):
            raw_t = re.sub(r"<[^>]+>", "", it.get("DRETITLE") or "")
            raw_d = re.sub(r"<[^>]+>", "", it.get("DRECONTENT") or "")
            t = _h.unescape(raw_t).strip()
            d = _h.unescape(raw_d).strip()
            if name not in t:
                continue
            m = (re.search(r"第\s*(\d+)\s*[集期]", t)
                 or re.search(r"(\d{8})", t)
                 or re.search(r"[Ee][Pp]?\s*(\d+)", t))
            if not m:
                continue
            num = m.group(1)
            n = int(num[-2:]) if len(num) == 8 else int(num)
            if n <= 0 or n in result:
                continue
            title = re.sub(r"^.*?第\s*\d+\s*[集期][：:\s]*", "", t).strip() or t
            if len(title) > 60:
                title = title[:60]
            result[n] = (title, d if len(d) >= 20 else "")
        return result

    def __tmdb_fetch_images(self, tid, season):
        try:
            url = f"https://www.themoviedb.org/tv/{tid}/season/{season}?language=zh-CN"
            resp = requests.get(url, headers={"User-Agent": self._UA}, timeout=15)
            html = resp.text
            if resp.status_code != 200 or "Page Not Found" in html[:4000]:
                return {}
        except Exception:
            return {}
        result = {}
        for m in re.finditer(r'data-url="[^"]*/episode/(\d+)[^"]*"', html):
            n = int(m.group(1))
            pos = m.start()
            blk = html[pos:pos+2500]
            img = re.search(r'<img[^>]+(?:data-src|src)="([^"]+)"', blk)
            if img:
                src = img.group(1)
                if src.startswith('/'):
                    src = 'https://www.themoviedb.org' + src
                result[n] = src
        return result

    def __emby_get(self, base, key, path, params=None):
        import urllib.request
        url = f"{base.rstrip('/')}/emby{path}?api_key={key}"
        if params:
            url += "&" + urllib.parse.urlencode(params)
        try:
            req = urllib.request.Request(url, headers={"X-Emby-Token": key})
            resp = urllib.request.urlopen(req, timeout=30)
            return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.info(f"Emby GET {path} 失败: {e}")
            return None
    def __emby_post(self, base, key, path, body):
        import urllib.request
        url = f"{base.rstrip('/')}/emby{path}?api_key={key}"
        data = json.dumps(body).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=data,
                headers={"X-Emby-Token": key, "Content-Type": "application/json"},
                method="POST")
            resp = urllib.request.urlopen(req, timeout=30)
            return resp.status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception as e:
            logger.info(f"Emby POST {path} 失败: {e}")
            return 0
    def __get_uid(self, base, key):
        users = self.__emby_get(base, key, "/Users")
        if users and len(users) > 0:
            return users[0].get("Id")
        return None

    def __skip(self, name, sn, kind, detail=""):
        """记录丢弃项，带类型标签，插件页/通知可直接看"""
        self._report.setdefault("skipped", []).append({
            "series": name, "season": sn, "kind": kind, "detail": detail})
        self._report.setdefault("skip_kinds", {})
        self._report["skip_kinds"][kind] = self._report["skip_kinds"].get(kind, 0) + 1

    def __emby_upload_image(self, base, key, eid, img_url, itype="Primary"):
        """用 Emby 远程下载接口写分集图，POST item 是写不进图的"""
        path = f"/Items/{eid}/RemoteImages/Download"
        q = urllib.parse.urlencode({"Type": itype, "ImageUrl": img_url})
        url = f"{base.rstrip('/')}/emby{path}?api_key={key}&{q}"
        try:
            req = urllib.request.Request(url, data=b"", headers={"X-Emby-Token": key}, method="POST")
            resp = urllib.request.urlopen(req, timeout=30)
            return resp.status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:
            return 0

    def __series_selected(self, sid, name):
        raw = (self._only_series or '').strip()
        if not raw:
            return True
        parts = [x.strip() for x in raw.split(',') if x.strip()]
        return any(x == sid or x == name or x in name for x in parts)

    def __notify_done(self):
        if not self._notify or NotificationType is None:
            return
        try:
            title = "【元数据补全】完成"
            text = f"成功 {self._report.get('ok',0)} / 失败 {self._report.get('fail',0)} / 缩略图 {self._report.get('img',0)} / 跳过 {len(self._report.get('skipped',[]))}"
            skipped = self._report.get("skipped") or []
            if skipped:
                lines = []
                for s in skipped[:10]:
                    d = s.get("detail") or ""
                    lines.append(f"- {s.get('series') or ''} S{s.get('season') or '?'} [{s.get('kind') or '?'}]{': ' + d if d else ''}")
                text += "\n" + "\n".join(lines)
            self.post_message(mtype=NotificationType.Plugin, title=title, text=text)
        except Exception as e:
            logger.info(f"通知发送失败: {e}")

    def stop_service(self):
        """停止时清理"""
        self._enabled = False
