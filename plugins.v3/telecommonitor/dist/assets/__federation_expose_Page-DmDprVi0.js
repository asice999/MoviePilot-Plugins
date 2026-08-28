import { importShared } from './__federation_fn_import-1piVvliX.js';

const {toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createVNode:_createVNode,createElementVNode:_createElementVNode,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "text-h4" };
const _hoisted_2 = { class: "text-caption" };
const _hoisted_3 = { class: "text-h4" };
const _hoisted_4 = { class: "text-h4" };
const _hoisted_5 = { class: "text-caption" };
const _hoisted_6 = { class: "text-h6" };
const _hoisted_7 = { class: "text-caption" };

const {ref,onMounted,inject} = await importShared('vue');



const _sfc_main = {
  __name: 'Page',
  props: {
  api: { type: Object, required: true }
},
  setup(__props) {

const props = __props;

const api = props.api;
const loading = ref(false);
const error = ref('');
const summary = ref(null);
const history = ref([]);

async function loadOverview() {
  try {
    const res = await api.get('plugin/TelecomMonitor/overview');
    if (res.success) {
      summary.value = res.data?.summary || null;
    }
  } catch (e) { /* ignore */ }
}

async function loadHistory() {
  try {
    const res = await api.get('plugin/TelecomMonitor/history?limit=30');
    if (res.success) {
      history.value = res.data || [];
    }
  } catch (e) { /* ignore */ }
}

async function query() {
  loading.value = true;
  error.value = '';
  try {
    const res = await api.get('plugin/TelecomMonitor/query');
    if (res.success) {
      summary.value = res.data;
      await loadHistory();
    } else {
      error.value = res.error || '查询失败';
    }
  } catch (e) {
    error.value = String(e);
  } finally {
    loading.value = false;
  }
}

function formatGB(kb) {
  return kb ? (kb / 1024 / 1024 / 1024).toFixed(2) : '0.00'
}

onMounted(() => {
  loadOverview();
  loadHistory();
});

return (_ctx, _cache) => {
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_list_item_title = _resolveComponent("v-list-item-title");
  const _component_v_list_item_subtitle = _resolveComponent("v-list-item-subtitle");
  const _component_v_progress_linear = _resolveComponent("v-progress-linear");
  const _component_v_list_item = _resolveComponent("v-list-item");
  const _component_v_list = _resolveComponent("v-list");
  const _component_v_table = _resolveComponent("v-table");
  const _component_v_container = _resolveComponent("v-container");

  return (_openBlock(), _createBlock(_component_v_container, { fluid: "" }, {
    default: _withCtx(() => [
      (error.value)
        ? (_openBlock(), _createBlock(_component_v_alert, {
            key: 0,
            type: "error",
            density: "compact",
            class: "mb-3"
          }, {
            default: _withCtx(() => [
              _createTextVNode(_toDisplayString(error.value), 1)
            ]),
            _: 1
          }))
        : _createCommentVNode("", true),
      _createVNode(_component_v_row, null, {
        default: _withCtx(() => [
          _createVNode(_component_v_col, { cols: "12" }, {
            default: _withCtx(() => [
              _createVNode(_component_v_card, null, {
                default: _withCtx(() => [
                  _createVNode(_component_v_card_title, { class: "d-flex align-center" }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_icon, {
                        icon: "mdi-cellphone-check",
                        class: "mr-2",
                        color: "primary"
                      }),
                      _cache[1] || (_cache[1] = _createTextVNode(" 电信套餐监控 ", -1)),
                      _createVNode(_component_v_spacer),
                      _createVNode(_component_v_btn, {
                        size: "small",
                        color: "primary",
                        variant: "tonal",
                        loading: loading.value,
                        onClick: query
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_icon, {
                            icon: "mdi-refresh",
                            size: "small",
                            class: "mr-1"
                          }),
                          _cache[0] || (_cache[0] = _createTextVNode(" 立即查询 ", -1))
                        ]),
                        _: 1
                      }, 8, ["loading"])
                    ]),
                    _: 1
                  }),
                  (summary.value)
                    ? (_openBlock(), _createBlock(_component_v_card_text, { key: 0 }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_row, null, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_col, {
                                cols: "12",
                                sm: "6",
                                md: "3"
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_v_card, {
                                    variant: "tonal",
                                    color: "primary"
                                  }, {
                                    default: _withCtx(() => [
                                      _createVNode(_component_v_card_text, { class: "text-center" }, {
                                        default: _withCtx(() => [
                                          _createElementVNode("div", _hoisted_1, [
                                            _createTextVNode(_toDisplayString(formatGB(summary.value.commonUse)), 1),
                                            _createElementVNode("span", _hoisted_2, " / " + _toDisplayString(formatGB(summary.value.commonTotal)) + " GB", 1)
                                          ]),
                                          _cache[2] || (_cache[2] = _createElementVNode("div", { class: "text-caption" }, "通用流量", -1))
                                        ]),
                                        _: 1
                                      })
                                    ]),
                                    _: 1
                                  })
                                ]),
                                _: 1
                              }),
                              _createVNode(_component_v_col, {
                                cols: "12",
                                sm: "6",
                                md: "3"
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_v_card, {
                                    variant: "tonal",
                                    color: "success"
                                  }, {
                                    default: _withCtx(() => [
                                      _createVNode(_component_v_card_text, { class: "text-center" }, {
                                        default: _withCtx(() => [
                                          _createElementVNode("div", _hoisted_3, _toDisplayString((summary.value.balance / 100).toFixed(2)), 1),
                                          _cache[3] || (_cache[3] = _createElementVNode("div", { class: "text-caption" }, "余额（元）", -1))
                                        ]),
                                        _: 1
                                      })
                                    ]),
                                    _: 1
                                  })
                                ]),
                                _: 1
                              }),
                              _createVNode(_component_v_col, {
                                cols: "12",
                                sm: "6",
                                md: "3"
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_v_card, {
                                    variant: "tonal",
                                    color: "info"
                                  }, {
                                    default: _withCtx(() => [
                                      _createVNode(_component_v_card_text, { class: "text-center" }, {
                                        default: _withCtx(() => [
                                          _createElementVNode("div", _hoisted_4, [
                                            _createTextVNode(_toDisplayString(summary.value.voiceUsage), 1),
                                            _createElementVNode("span", _hoisted_5, " / " + _toDisplayString(summary.value.voiceTotal) + " min", 1)
                                          ]),
                                          _cache[4] || (_cache[4] = _createElementVNode("div", { class: "text-caption" }, "语音通话", -1))
                                        ]),
                                        _: 1
                                      })
                                    ]),
                                    _: 1
                                  })
                                ]),
                                _: 1
                              }),
                              _createVNode(_component_v_col, {
                                cols: "12",
                                sm: "6",
                                md: "3"
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_v_card, {
                                    variant: "tonal",
                                    color: "warning"
                                  }, {
                                    default: _withCtx(() => [
                                      _createVNode(_component_v_card_text, { class: "text-center" }, {
                                        default: _withCtx(() => [
                                          _createElementVNode("div", _hoisted_6, _toDisplayString(summary.value.phonenum), 1),
                                          _createElementVNode("div", _hoisted_7, _toDisplayString(summary.value.createTime), 1)
                                        ]),
                                        _: 1
                                      })
                                    ]),
                                    _: 1
                                  })
                                ]),
                                _: 1
                              })
                            ]),
                            _: 1
                          }),
                          (summary.value.flowItems && summary.value.flowItems.length)
                            ? (_openBlock(), _createBlock(_component_v_row, {
                                key: 0,
                                class: "mt-2"
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_v_col, { cols: "12" }, {
                                    default: _withCtx(() => [
                                      _createVNode(_component_v_list, { density: "compact" }, {
                                        default: _withCtx(() => [
                                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(summary.value.flowItems, (item) => {
                                            return (_openBlock(), _createBlock(_component_v_list_item, {
                                              key: item.name
                                            }, {
                                              prepend: _withCtx(() => [
                                                _createVNode(_component_v_icon, {
                                                  icon: "mdi-waves",
                                                  color: "primary"
                                                })
                                              ]),
                                              append: _withCtx(() => [
                                                _createVNode(_component_v_progress_linear, {
                                                  "model-value": item.total > 0 ? (item.use / item.total * 100) : 0,
                                                  height: "8",
                                                  rounded: "",
                                                  color: item.total > 0 && item.use / item.total > 0.9 ? 'error' : 'primary',
                                                  class: "mt-2",
                                                  style: {"width":"120px"}
                                                }, null, 8, ["model-value", "color"])
                                              ]),
                                              default: _withCtx(() => [
                                                _createVNode(_component_v_list_item_title, null, {
                                                  default: _withCtx(() => [
                                                    _createTextVNode(_toDisplayString(item.name), 1)
                                                  ]),
                                                  _: 2
                                                }, 1024),
                                                _createVNode(_component_v_list_item_subtitle, null, {
                                                  default: _withCtx(() => [
                                                    _createTextVNode(" 已用 " + _toDisplayString(formatGB(item.use)) + " / " + _toDisplayString(formatGB(item.total)) + " GB（剩余 " + _toDisplayString(formatGB(item.balance)) + " GB） ", 1)
                                                  ]),
                                                  _: 2
                                                }, 1024)
                                              ]),
                                              _: 2
                                            }, 1024))
                                          }), 128))
                                        ]),
                                        _: 1
                                      })
                                    ]),
                                    _: 1
                                  })
                                ]),
                                _: 1
                              }))
                            : _createCommentVNode("", true)
                        ]),
                        _: 1
                      }))
                    : (_openBlock(), _createBlock(_component_v_card_text, { key: 1 }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_alert, {
                            type: "info",
                            density: "compact"
                          }, {
                            default: _withCtx(() => [...(_cache[5] || (_cache[5] = [
                              _createTextVNode("暂无数据，点击\"立即查询\"获取当前套餐用量", -1)
                            ]))]),
                            _: 1
                          })
                        ]),
                        _: 1
                      }))
                ]),
                _: 1
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createVNode(_component_v_row, { class: "mt-2" }, {
        default: _withCtx(() => [
          _createVNode(_component_v_col, { cols: "12" }, {
            default: _withCtx(() => [
              _createVNode(_component_v_card, null, {
                default: _withCtx(() => [
                  _createVNode(_component_v_card_title, null, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_icon, {
                        icon: "mdi-history",
                        class: "mr-2"
                      }),
                      _cache[6] || (_cache[6] = _createTextVNode(" 查询历史 ", -1))
                    ]),
                    _: 1
                  }),
                  (history.value.length)
                    ? (_openBlock(), _createBlock(_component_v_card_text, { key: 0 }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_table, { density: "compact" }, {
                            default: _withCtx(() => [
                              _cache[7] || (_cache[7] = _createElementVNode("thead", null, [
                                _createElementVNode("tr", null, [
                                  _createElementVNode("th", null, "时间"),
                                  _createElementVNode("th", null, "流量"),
                                  _createElementVNode("th", null, "通话"),
                                  _createElementVNode("th", null, "余额")
                                ])
                              ], -1)),
                              _createElementVNode("tbody", null, [
                                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(history.value, (item) => {
                                  return (_openBlock(), _createElementBlock("tr", {
                                    key: item.time
                                  }, [
                                    _createElementVNode("td", null, _toDisplayString(item.time), 1),
                                    _createElementVNode("td", null, _toDisplayString(item.common_use_gb) + " / " + _toDisplayString(item.common_total_gb) + " GB", 1),
                                    _createElementVNode("td", null, _toDisplayString(item.voice_use) + " min", 1),
                                    _createElementVNode("td", null, _toDisplayString((item.balance / 100).toFixed(2)) + " 元", 1)
                                  ]))
                                }), 128))
                              ])
                            ]),
                            _: 1
                          })
                        ]),
                        _: 1
                      }))
                    : (_openBlock(), _createBlock(_component_v_card_text, { key: 1 }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_alert, {
                            type: "info",
                            density: "compact"
                          }, {
                            default: _withCtx(() => [...(_cache[8] || (_cache[8] = [
                              _createTextVNode("暂无历史记录", -1)
                            ]))]),
                            _: 1
                          })
                        ]),
                        _: 1
                      }))
                ]),
                _: 1
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      })
    ]),
    _: 1
  }))
}
}

};

export { _sfc_main as default };
