import { importShared } from './__federation_fn_import-1piVvliX.js';

const {toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createVNode:_createVNode} = await importShared('vue');


const {ref,onMounted} = await importShared('vue');



const _sfc_main = {
  __name: 'Config',
  props: {
  api: { type: Object, required: true }
},
  setup(__props) {

const props = __props;

const api = props.api;
const phonenum = ref('');
const password = ref('');
const testing = ref(false);
const error = ref('');
const overview = ref(null);

async function loadOverview() {
  try {
    const res = await api.get('plugin/TelecomMonitor/overview');
    if (res.success) {
      overview.value = res.data;
      phonenum.value = res.data?.phonenum || '';
    }
  } catch (e) { /* ignore */ }
}

async function testLogin() {
  testing.value = true;
  error.value = '';
  try {
    const res = await api.post('plugin/TelecomMonitor/login', {
      phonenum: phonenum.value,
      password: password.value
    });
    if (res.success) {
      overview.value = { ...(overview.value || {}), phonenum: phonenum.value };
    } else {
      error.value = res.error || '登录失败';
    }
  } catch (e) {
    error.value = String(e);
  } finally {
    testing.value = false;
  }
}

onMounted(loadOverview);

return (_ctx, _cache) => {
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_form = _resolveComponent("v-form");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_list_item_title = _resolveComponent("v-list-item-title");
  const _component_v_list_item_subtitle = _resolveComponent("v-list-item-subtitle");
  const _component_v_list_item = _resolveComponent("v-list-item");
  const _component_v_list = _resolveComponent("v-list");
  const _component_v_row = _resolveComponent("v-row");
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
          _createVNode(_component_v_col, {
            cols: "12",
            md: "6"
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_card, null, {
                default: _withCtx(() => [
                  _createVNode(_component_v_card_title, null, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_icon, {
                        icon: "mdi-account-key",
                        class: "mr-2",
                        color: "primary"
                      }),
                      _cache[2] || (_cache[2] = _createTextVNode(" 账号配置 ", -1))
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_v_card_text, null, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_form, null, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_text_field, {
                            modelValue: phonenum.value,
                            "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((phonenum).value = $event)),
                            label: "手机号",
                            placeholder: "11位手机号",
                            outlined: "",
                            dense: ""
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_v_text_field, {
                            modelValue: password.value,
                            "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((password).value = $event)),
                            label: "电信服务密码",
                            type: "password",
                            autocomplete: "new-password",
                            outlined: "",
                            dense: ""
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_v_alert, {
                            type: "info",
                            density: "compact",
                            class: "mb-3"
                          }, {
                            default: _withCtx(() => [...(_cache[3] || (_cache[3] = [
                              _createTextVNode(" 配置保存后，插件每日自动查询。Token 过期自动重新登录。 ", -1)
                            ]))]),
                            _: 1
                          }),
                          _createVNode(_component_v_btn, {
                            color: "primary",
                            loading: testing.value,
                            onClick: testLogin
                          }, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_icon, {
                                icon: "mdi-lock-check",
                                size: "small",
                                class: "mr-1"
                              }),
                              _cache[4] || (_cache[4] = _createTextVNode(" 测试登录 ", -1))
                            ]),
                            _: 1
                          }, 8, ["loading"])
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
          _createVNode(_component_v_col, {
            cols: "12",
            md: "6"
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_card, null, {
                default: _withCtx(() => [
                  _createVNode(_component_v_card_title, null, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_icon, {
                        icon: "mdi-information-outline",
                        class: "mr-2",
                        color: "info"
                      }),
                      _cache[5] || (_cache[5] = _createTextVNode(" 当前状态 ", -1))
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_v_card_text, null, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_list, { density: "compact" }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_list_item, null, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_list_item_title, null, {
                                default: _withCtx(() => [...(_cache[6] || (_cache[6] = [
                                  _createTextVNode("手机号", -1)
                                ]))]),
                                _: 1
                              }),
                              _createVNode(_component_v_list_item_subtitle, null, {
                                default: _withCtx(() => [
                                  _createTextVNode(_toDisplayString(overview.value?.phonenum || '未配置'), 1)
                                ]),
                                _: 1
                              })
                            ]),
                            _: 1
                          }),
                          _createVNode(_component_v_list_item, null, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_list_item_title, null, {
                                default: _withCtx(() => [...(_cache[7] || (_cache[7] = [
                                  _createTextVNode("上次查询", -1)
                                ]))]),
                                _: 1
                              }),
                              _createVNode(_component_v_list_item_subtitle, null, {
                                default: _withCtx(() => [
                                  _createTextVNode(_toDisplayString(overview.value?.last_query_time || '从未查询'), 1)
                                ]),
                                _: 1
                              })
                            ]),
                            _: 1
                          }),
                          _createVNode(_component_v_list_item, null, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_list_item_title, null, {
                                default: _withCtx(() => [...(_cache[8] || (_cache[8] = [
                                  _createTextVNode("定时任务", -1)
                                ]))]),
                                _: 1
                              }),
                              _createVNode(_component_v_list_item_subtitle, null, {
                                default: _withCtx(() => [
                                  _createTextVNode(_toDisplayString(overview.value?.cron || '-') + "（" + _toDisplayString(overview.value?.enabled ? '已启用' : '未启用') + "）", 1)
                                ]),
                                _: 1
                              })
                            ]),
                            _: 1
                          }),
                          _createVNode(_component_v_list_item, null, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_list_item_title, null, {
                                default: _withCtx(() => [...(_cache[9] || (_cache[9] = [
                                  _createTextVNode("历史记录", -1)
                                ]))]),
                                _: 1
                              }),
                              _createVNode(_component_v_list_item_subtitle, null, {
                                default: _withCtx(() => [
                                  _createTextVNode(_toDisplayString(overview.value?.history_count || 0) + " 条", 1)
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
