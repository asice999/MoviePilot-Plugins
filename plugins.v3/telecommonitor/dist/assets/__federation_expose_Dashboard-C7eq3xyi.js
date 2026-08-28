import { importShared } from './__federation_fn_import-1piVvliX.js';

const {toDisplayString:_toDisplayString,createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,createTextVNode:_createTextVNode,createBlock:_createBlock} = await importShared('vue');


const _hoisted_1 = { key: 0 };
const _hoisted_2 = { class: "text-h6" };
const _hoisted_3 = { class: "text-h6" };
const _hoisted_4 = { class: "text-h6" };
const _hoisted_5 = { class: "text-h6" };

const {ref,onMounted} = await importShared('vue');



const _sfc_main = {
  __name: 'Dashboard',
  props: {
  api: { type: Object, required: true }
},
  setup(__props) {

const props = __props;

const api = props.api;
const summary = ref(null);

function formatGB(kb) {
  return kb ? (kb / 1024 / 1024 / 1024).toFixed(2) : '0.00'
}

onMounted(async () => {
  try {
    const res = await api.get('plugin/TelecomMonitor/overview');
    if (res.success) {
      summary.value = res.data?.summary || null;
    }
  } catch (e) { /* ignore */ }
});

return (_ctx, _cache) => {
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_alert = _resolveComponent("v-alert");

  return (summary.value)
    ? (_openBlock(), _createElementBlock("div", _hoisted_1, [
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
                    _createVNode(_component_v_card_text, { class: "text-center pa-3" }, {
                      default: _withCtx(() => [
                        _createElementVNode("div", _hoisted_2, _toDisplayString(formatGB(summary.value.commonUse)) + " / " + _toDisplayString(formatGB(summary.value.commonTotal)) + " GB", 1),
                        _cache[0] || (_cache[0] = _createElementVNode("div", { class: "text-caption" }, "通用流量", -1))
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
                    _createVNode(_component_v_card_text, { class: "text-center pa-3" }, {
                      default: _withCtx(() => [
                        _createElementVNode("div", _hoisted_3, _toDisplayString((summary.value.balance / 100).toFixed(2)) + " 元", 1),
                        _cache[1] || (_cache[1] = _createElementVNode("div", { class: "text-caption" }, "余额", -1))
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
                    _createVNode(_component_v_card_text, { class: "text-center pa-3" }, {
                      default: _withCtx(() => [
                        _createElementVNode("div", _hoisted_4, _toDisplayString(summary.value.voiceUsage) + " min", 1),
                        _cache[2] || (_cache[2] = _createElementVNode("div", { class: "text-caption" }, "通话", -1))
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
                    _createVNode(_component_v_card_text, { class: "text-center pa-3" }, {
                      default: _withCtx(() => [
                        _createElementVNode("div", _hoisted_5, _toDisplayString(summary.value.phonenum), 1),
                        _cache[3] || (_cache[3] = _createElementVNode("div", { class: "text-caption" }, "手机号", -1))
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
        })
      ]))
    : (_openBlock(), _createBlock(_component_v_alert, {
        key: 1,
        type: "info",
        density: "compact",
        class: "mt-2"
      }, {
        default: _withCtx(() => [...(_cache[4] || (_cache[4] = [
          _createTextVNode("暂无套餐数据，请先查询", -1)
        ]))]),
        _: 1
      }))
}
}

};

export { _sfc_main as default };
