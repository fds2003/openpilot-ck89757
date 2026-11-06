# libtouka.so 逆向分析报告

> 分析日期：2026-10-11
> 文件：`lib/armeabi-v7a/libtouka.so`（高德悬浮窗核心库，133,468 字节）
> 来源：高德地图车机版 7.5.0 靓华修改版 APK

---

## 1. 基本信息

| 属性 | 值 |
|------|-----|
| 格式 | ELF 32-bit LSB shared object |
| 架构 | ARM EABI5 (armeabi-v7a) |
| 目标系统 | Android 19 (API 19 = 4.4.3) |
| 编译器 | NDK r25c，clang 14.0.7，LLD 14.0.7 |
| 符号 | **stripped**（仅保留动态导出） |
| BuildID | `a93911c087406272847e4a9984ca5783e97d6cd3` |
| 依赖 | libc.so / libdl.so / liblog.so / libm.so |

---

## 2. 导出符号（17 个 JNI 函数，4 个类）

### 2.1 `tech.touka.plugin.amap.ControlReceiver`（1 个）

| 地址 | 大小 | 函数 | 说明 |
|------|------|------|------|
| `0xca11` | 956 | `onReceive(Context, Intent)` | 广播接收入口 |

### 2.2 `touka.a`（1 个）

| 地址 | 大小 | 函数 | 说明 |
|------|------|------|------|
| `0xcdcd` | 1268 | `a(Application)` | **入口**：初始化 + 注册回调 |

### 2.3 `touka.b`（8 个，Activity 生命周期回调）

| 地址 | 大小 | 函数 |
|------|------|------|
| `0xd2c1` | 50 | `onActivityCreated(Activity, Bundle)` |
| `0xd2f3` | 30 | `onActivityDestroyed(Activity)` |
| `0xd311` | 1492 | `onActivityPaused(Activity)` |
| `0xd8e5` | 2052 | `onActivityResumed(Activity)` |
| `0xe0e9` | 50 | `onActivitySaveInstanceState(Activity, Bundle)` |
| `0xe11d` | 1932 | `onActivityStarted(Activity)` |
| `0xe8a9` | 30 | `onActivityStopped(Activity)` |

（8 个方法正好是 `Application.ActivityLifecycleCallbacks` 接口的全部方法）

### 2.4 `touka.c`（5 个，悬浮窗管理 + Intent 处理）

| 地址 | 大小 | 函数 | 说明 |
|------|------|------|------|
| `0xe8c9` | 912 | `a()` | 悬浮窗管理 |
| `0xec59` | 432 | `b()` | 悬浮窗管理 |
| `0xee09` | 968 | `c(Context)` | 上下文相关 |
| `0xf1d1` | 3416 | `d(Intent)` | **最大函数**：Intent/广播处理 |
| `0xff29` | 1452 | `e()` | 悬浮窗管理 |

### 2.5 `touka.d`（3 个，悬浮窗 View）

| 地址 | 大小 | 函数 | 说明 |
|------|------|------|------|
| `0x104d5` | 300 | `a()` | View 创建 |
| `0x10601` | 432 | `b()` | View 管理 |
| `0x107b1` | 676 | `c()` | View 渲染 |

---

## 3. 完整机制（核心结论）

### 3.1 关键发现：监控 `MainMapActivity`

字符串 `MainMapActivity` 是核心线索——插件通过 `getClass().getSimpleName()` 判断当前 Activity 是否是**高德地图主界面**，以此决定悬浮窗的显示/隐藏。

### 3.2 工作流程

```
[启动] FloatPluginManager.init(Application)
          ↓
        loadLibrary("touka")
          ↓
        touka.a.a(Application)   ← native 入口
          ↓
        ┌─────────────────────────────────────────┐
        │ 1. registerActivityLifecycleCallbacks   │  注册 touka.b 监听
        │ 2. 注册 ControlReceiver 广播             │  监听 showmap/closemap
        └─────────────────────────────────────────┘
          ↓
        [运行时] touka.b 监控每个 Activity 生命周期
          ↓
        getClass().getSimpleName() == "MainMapActivity" ?
          ↓
    ┌───────────────┴───────────────┐
    │ YES                           │ NO
    │ onPaused/Stopped → 创建悬浮窗  │ 忽略
    │ onResumed/Started → 移除悬浮窗 │
    └───────────────────────────────┘
          ↓
        [广播手动控制]
        com.autonavi.plus.showmap  → 显示悬浮窗
        com.autonavi.plus.closemap → 关闭悬浮窗
```

### 3.3 悬浮窗渲染（touka.d）

```
getSystemService(WindowManager)
  ↓
创建 SurfaceView + FrameLayout + RelativeLayout$LayoutParams
  ↓
addView → 系统级悬浮窗显示
  ↓
removeViewImmediate / removeAllViews → 移除
```

---

## 4. 关键字符串证据

| 字符串 | 作用 |
|--------|------|
| `MainMapActivity` | **监控目标 Activity**（核心） |
| `com.autonavi.plus.showmap` | 广播：显示悬浮窗 |
| `com.autonavi.plus.closemap` | 广播：关闭悬浮窗 |
| `registerActivityLifecycleCallbacks` | 注册生命周期监听 |
| `registerReceiver` / `addAction` | 注册广播接收器 |
| `getSystemService` | 获取系统服务（WindowManager） |
| `WindowManager` / `WindowManager$LayoutParams` | 悬浮窗布局 |
| `SurfaceView` / `FrameLayout` / `RelativeLayout$LayoutParams` | 悬浮窗 UI 组件 |
| `addView` / `removeViewImmediate` / `removeAllViews` | 视图增删 |
| `setLayoutParams` / `findViewById` | 视图管理 |
| `getAction` / `getIntExtra` | 解析 Intent |
| `getClass` / `getSimpleName` | 判断 Activity 类型 |
| `AtomicBoolean` | 线程安全标志 |
| `Build$VERSION` / `SDK_INT` | Android 版本判断 |
| `height` / `gravity` / `window` / `pixel` | UI 属性 |
| `ControlReceiver: action:` | 日志（广播） |
| `onActivityResumed:` / `onActivityPaused:` / `onActivityStarted:` | 日志（生命周期） |

---

## 5. 与 Java 侧的对应关系

| Native 函数 | Java 类（smali） | 作用 |
|-------------|-----------------|------|
| `Java_touka_a_a` | `touka/a.a(Application)` | 入口初始化 |
| `Java_touka_b_onActivity*` | `touka/b`（ActivityLifecycleCallbacks 实现） | 生命周期监控 |
| `Java_touka_c_*` | `touka/c` | 悬浮窗管理 + Intent 处理 |
| `Java_touka_d_*` | `touka/d` | 悬浮窗 View 渲染 |
| `Java_tech_..._ControlReceiver_onReceive` | `ControlReceiver.onReceive` | 广播接收 |

---

## 6. 移植结论（对高版本 APK 的启示）

### 6.1 为什么 9.1.0 能移植

- 架构匹配（armeabi-v7a），libtouka.so 可直接复用
- 悬浮窗机制依赖 `MainMapActivity`（高德地图类名稳定），9.1.0 大概率仍是这个类名
- 注入点结构一致（`MapApplicationProxy.onCreate`）

### 6.2 9.5.0 的额外障碍（除 minSdk/arm64 外）

即使有 arm64 版 so，还需确认：
- 9.5.0 的地图主 Activity 是否还叫 `MainMapActivity`（高德可能重构改名）
- 若类名变了，悬浮窗监控会失效（需改 so 内的字符串）

### 6.3 若悬浮窗不生效的排查方向

1. **类名变了** → 用 logcat 看 `onActivityPaused:` 日志是否触发，确认 Activity 类名
2. **广播未注册** → 检查 `com.autonavi.plus.showmap/closemap` 广播是否被发送
3. **权限** → `SYSTEM_ALERT_WINDOW` 需平台签名或手动授权
4. **so 未加载** → 检查 `FloatPluginManager.init` 注入点是否生效

---

*本报告基于 ELF 导出符号表 + 字符串 + 入口函数反汇编的静态分析，未动态调试。*
