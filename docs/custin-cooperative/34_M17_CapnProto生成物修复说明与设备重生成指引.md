# 34 M-17 Cap'n Proto 生成物修复说明与设备重生成指引

> 对应台账：30 号主索引表 M-17（capnp C++ 生成物未随 schema 重跑）
> 取证基线：E:/code/openpilot-ck89757 @ 70ba3d8；cereal/custom.capnp、cereal/gen/cpp/custom.capnp.h 与 .c++、cereal/SConscript、.gitignore
> 日期：2026-11-03
> 结论：本机工具链缺失，无法真正重生成；不伪造生成物。已界定风险、给出设备侧一步修复命令，并加防漂移注释。M-17 状态改为阻塞（需 C3 工具链）。

---

## 一、为什么本机不能修

| 工具 | 本机状态 |
| :--- | :--- |
| capnp | 不可用 |
| capnpc-c++ | 不可用 |
| scons | 不可用 |
| Python capnp 模块 | 不可用 |
| 仓库内预编译 capnpc 二进制 | 无 |

cereal/SConscript 的生成规则为：
env.Command(生成物, schema_files, "capnpc --src-prefix=... -o c++:gen/cpp/")

没有 capnpc 就无法产出合法生成物。

## 二、生成物陈旧的范围（不止一个数字）

| 位置 | 实测 | 应为 |
| :--- | :--- | :--- |
| custom.capnp.h:70 | CAPNP_DECLARE_STRUCT_HEADER(aedffd8f31e7b55d, 8, 0) | 由 capnpc 按 17 字段重新计算 |
| custom.capnp.c++:914 | m_... 数组仅 15 项 | 17 项 |
| custom.capnp.c++:915 | i_... 数组为 0 到 14 共 15 项 | 0 到 16 共 17 项 |
| custom.capnp.c++:657 / :917-918 | AlignedData<253> schema blob；RawSchema 字段数为 15 | 按新 schema 重新编码 |
| cereal/custom.capnp:59-78 | 17 字段（@0 到 @16），新增 overtakeMode @15、lidarBehindVdistTime @16 | 参考基准 |

即：生成物的 schema 二进制编码、字段索引表、字段数全是 15 字段版。只把 8 改成 9 是伪造——C++ Reader 依然没有 @15 / @16 的访问器，schema blob 仍是旧的。本轮未改动任何生成物文件。

## 三、风险界定（当前无运行时错误）

1. 全仓检索 cc / cpp / cxx / h / hpp / c 源码，没有任何代码 include custom.capnp.h 或引用 AmapNavi。C++ 侧不解析该结构体。
2. Python 侧 cereal/messaging.py 通过 capnp 动态加载 custom.capnp 源码，不依赖 C++ 生成物。
3. 因此陈旧生成物当前不会造成解码错乱；风险是：将来若 C++ 侧开始使用 AmapNavi，会按 15 字段旧布局解码；以及生成物与 schema 长期漂移。
4. 版本控制状态异常：.gitignore:48 已忽略 cereal/gen，但生成物仍被 git 跟踪（历史提交带入），这是漂移的土壤。本轮未改动版本控制状态（git rm --cached 属破坏性操作，需单独授权）。

## 四、设备侧一步修复（在 C3 / AGNOS 上执行）

SConscript 的 target 依赖 schema_files，且 cereal/custom.capnp（2026-11-02 21:49）比生成物（2026-10-28 09:18）新，scons 会自动判定需要重跑，无需手工触发 capnpc。

**首选：一键脚本（含自动验收）**。本轮已生成 tools/regen_capnp_gen.sh，默认只重生成并校验、不提交；加 --commit 才 git add + commit，且永不 push：

    cd /data/openpilot
    bash tools/regen_capnp_gen.sh             # 重生成 + 验收
    git diff -- cereal/gen/cpp/custom.capnp.h cereal/gen/cpp/custom.capnp.c++
    bash tools/regen_capnp_gen.sh --commit    # 验收通过后再提交

脚本验收判据：生成物字段索引数组项数与 schema 字段数一致（17）、getOvertakeMode / getLidarBehindVdistTime 两个 getter 存在、dataWordCount 不再是 8；任一不满足即退出且不提交。脚本会先打印 BEFORE / AFTER 便于对比。

**等价手动方式**：

    cd /data/openpilot
    touch cereal/custom.capnp && scons -j$(nproc) cereal/

验收判据（重生成后）：

    grep -n "CAPNP_DECLARE_STRUCT_HEADER(aedffd8f31e7b55d" cereal/gen/cpp/custom.capnp.h
    grep -n "i_aedffd8f31e7b55d" cereal/gen/cpp/custom.capnp.c++
    grep -n "getOvertakeMode\|getLidarBehindVdistTime" cereal/gen/cpp/custom.capnp.h

期望：dataWordCount 不再是 8（由 capnpc 按 17 字段计算，以工具输出为准）；i_ 数组含 0 到 16 共 17 项；新字段 getter 存在。若 scons 未触发，可强制：

    touch cereal/custom.capnp && scons -j$(nproc) cereal/

最后提交生成物：

    git add cereal/gen/cpp/custom.capnp.h cereal/gen/cpp/custom.capnp.c++
    git commit -m "chore(cereal): regenerate C++ schema bindings for AmapNavi 17 fields"

## 五、本轮已做的防漂移措施

在 cereal/SConscript 的 schema_files 定义前新增注释，明确：改任何 .capnp 后必须跑 scons 重生成并提交 gen/cpp 生成物，否则 C++ 按旧布局解码；并指向本文。纯注释，不改变构建行为。

## 六、台账状态

M-17 由未修改为阻塞（需 C3 工具链）：风险已界定（无 C++ 使用者）、修复路径已给出（设备侧 scons 一步完成）、本机不具备重生成条件。汇总表新增该状态类 1 条，未修由 8 条降为 7 条，总数仍 35。不标为已闭环，因为生成物当前仍是 15 字段版。

---

本文未修改任何生成物或工程代码；仅新增 SConscript 注释与本文档。所有 file:line 可复核。
