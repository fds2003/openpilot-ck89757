"""echo_cmd 远程命令网关（P0-3 / P1-4）。

轻量模块（仅 stdlib），供 carrot_man 与测试共同导入——消除测试抄写
生产逻辑副本导致的语义漂移（曾出现 shell=True 任意命令的错误副本）。

门控顺序（fail closed）：
1. CarrotEchoCmdEnable=0 → 拒绝（-1）
2. 行驶中（IsOnroad=1）→ 硬锁定（423）
3. 不在白名单 → 拒绝（-3）
4. 执行白名单闭包，异常兜底（-2），绝不 shell=True
"""


def handle_echo_cmd(json_obj, params, is_onroad, whitelist):
  """处理 echo_cmd 请求，返回 JSON 响应 dict。

  Args:
    json_obj: 含 'echo_cmd' 键的请求（调用方已确认键存在）。
    params: Params/UnifiedParams，读 CarrotEchoCmdEnable。
    is_onroad: 行驶状态。
    whitelist: {命令名: 返回 (exit_status, stdout, stderr) 或 CompletedProcess 的闭包}。
  """
  cmd_name = json_obj['echo_cmd']
  if not params.get_bool("CarrotEchoCmdEnable"):
    return {"echo_cmd": cmd_name, "exitStatus": -1, "result": "",
            "error": "echo_cmd is disabled by user switch (CarrotEchoCmdEnable=0)"}
  if is_onroad:
    return {"echo_cmd": cmd_name, "exitStatus": 423, "result": "",
            "error": "echo_cmd is locked during onroad driving for safety"}
  if cmd_name not in whitelist:
    return {"echo_cmd": cmd_name, "exitStatus": -3, "result": "",
            "error": f"S-1: command '{cmd_name}' not in whitelist. Allowed: {list(whitelist.keys())}"}
  try:
    result = whitelist[cmd_name]()
    if hasattr(result, "returncode"):
      exit_status, out, err = result.returncode, result.stdout or "", result.stderr or ""
    else:
      exit_status, out, err = result
    return {"echo_cmd": cmd_name, "exitStatus": exit_status, "result": out, "error": err}
  except Exception as e:
    return {"echo_cmd": cmd_name, "exitStatus": -2, "result": "", "error": str(e)}
