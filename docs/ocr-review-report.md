## 阿里巴巴代码审查报告

模型 **deepseek / deepseek-flash** · 审查文件 **99** 个 · 耗时 **26m0s** · Token **6,509,506**

### 发现 538 个问题

按级别：严重 7 · 高 69 · 中 310 · 低 152

#### 1. `tools/wix314/sdk/inc/apputil.h:37-41` · 高 / 缺陷

> argc 与 pArgv 是输出参数却被标注为 `__in`。这样静态分析（/analyze、SAL）会把它们当作入参检查“调用方必须已初始化”，也无法标记函数返回后这两个值已被写入，容易导致调用方使用未初始化变量或漏掉初始化，属于错误的接口契约声明。建议改为 `__out`（若要更精确描述数组长度，可用 `__out int* argc, __deref_out_ecount(*argc) LPWSTR** pArgv`）。

**现有代码**

```c
DAPI_(HRESULT) AppParseCommandLine(
    __in LPCWSTR wzCommandLine,
    __in int* argc,
    __in LPWSTR** pArgv
    );
```

**改进建议**

```c
DAPI_(HRESULT) AppParseCommandLine(
    __in LPCWSTR wzCommandLine,
    __out int* argc,
    __out LPWSTR** pArgv
    );
```

#### 2. `tools/wix314/sdk/inc/apputil.h:1` · 中 / 缺陷

> 该头文件使用 LPCWSTR、DWORD、HRESULT、LPWSTR 等 Windows 类型，却未包含 <windows.h>（同目录的 BalBaseBootstrapperApplication.h、IBootstrapperBAFunction.h 都显式包含）。若调用方第一个包含本头文件，将直接编译失败；依赖调用顺序的隐式前置依赖是脆弱设计。建议显式 `#include <windows.h>`（或项目统一的公共前置头）。

**现有代码**

```c
#pragma once
```

**改进建议**

```c
#pragma once

#include <windows.h>
```

#### 3. `tools/wix314/sdk/inc/apputil.h:29` · 中 / 缺陷

> `void AppInitializeUnsafe();` 在 C 编译单元中是“参数未指定”的旧式声明，不进行任何实参类型/个数检查，传入多余参数也能编译通过。既然本头文件用 `extern "C"` 同时面向 C 与 C++，应显式写 `(void)`。另外 AppInitializeUnsafe 明确跳过标准安全措施（DLL 预加载等），但没有任何文档说明适用场景与风险，建议补充注释，避免被误用于发布路径。

**现有代码**

```c
void DAPI AppInitializeUnsafe();
```

**改进建议**

```c
void DAPI AppInitializeUnsafe(void);
```

#### 4. `tools/wix314/sdk/inc/apputil.h:19-22` · 中 / 缺陷

> 未约束“空数组 / 计数为 0”的边界：当调用方不需要安全预加载 DLL 时，很自然会传 NULL 和 0，而 `__in_ecount` 会把 NULL 视为违反契约（静态分析告警），实现若直接遍历也可能解引用。建议改为 `__in_ecount_opt` 并在注释中说明 cSafelyLoadSystemDlls == 0 时数组可为 NULL（此时行为等同于 AppInitializeUnsafe）。同时 AppInitialize 是三者中唯一没有说明性注释的公共接口，建议补齐。

**现有代码**

```c
void DAPI AppInitialize(
    __in_ecount(cSafelyLoadSystemDlls) LPCWSTR rgsczSafelyLoadSystemDlls[],
    __in DWORD cSafelyLoadSystemDlls
    );
```

**改进建议**

```c
void DAPI AppInitialize(
    __in_ecount_opt(cSafelyLoadSystemDlls) LPCWSTR rgsczSafelyLoadSystemDlls[],
    __in DWORD cSafelyLoadSystemDlls
    );
```

#### 5. `tools/wix314/sdk/inc/apputil.h:15-17` · 中 / 可维护性

> 释放契约不完整：1) 未说明 AppParseCommandLine 失败时 argc/pArgv 的状态（是否被修改、是否为 NULL），调用方可能对未初始化的 argv 调用 AppFreeCommandLineArgs 造成非法释放；建议实现中失败时把两者置零并在此注明。2) AppFreeCommandLineArgs 的 argv 未标注可为 NULL，建议用 `__in_opt LPWSTR* argv` 并说明对 NULL 安全。3) 需明确约定释放方式（底层为 CommandLineToArgvW 的 LocalAlloc 分配，必须由本函数内部用 LocalFree 释放，不能与 free/delete[] 混用），否则跨模块内存分配器不一致时会崩溃。

**现有代码**

```c
void DAPI AppFreeCommandLineArgs(
    __in LPWSTR* argv
    );
```

**改进建议**

```c
void DAPI AppFreeCommandLineArgs(
    __in_opt LPWSTR* argv
    );
```

#### 6. `tools/wix314/sdk/inc/IBootstrapperBAFunction.h:9-11` · 中 / 缺陷

> `IBootstrapperBAFunction` 既没有继承 `IUnknown`（对比同目录 `IBootstrapperEngine.h` 使用 `DECLARE_INTERFACE_IID_(IBootstrapperEngine, IUnknown, ...)` 的做法），也没有虚析构函数，同时 `PFN_BOOTSTRAPPER_BA_FUNCTION_CREATE` 只有 Create 没有对应的 Destroy/Release。结果是：创建回调返回的对象由谁释放、何时释放完全没有契约约束，引擎通过基类指针销毁时还会因缺少虚析构而触发未定义行为（UB），长期运行/多次加载 BA 时容易泄漏或悬垂指针。建议至少补一个 `virtual ~IBootstrapperBAFunction() {}`，并与 Create 配对提供 `PFN_BOOTSTRAPPER_BA_FUNCTION_DESTROY`，或在头文件中明确注释所有权归属。

**现有代码**

```c
interface IBootstrapperBAFunction
{
    STDMETHOD(OnDetect)() = 0;
```

**改进建议**

```c
interface IBootstrapperBAFunction
{
    virtual ~IBootstrapperBAFunction() {}
    STDMETHOD(OnDetect)() = 0;
```

#### 7. `tools/wix314/sdk/inc/IBootstrapperBAFunction.h:7` · 中 / 缺陷

> `STDMETHOD` 宏来自 `objbase.h`/`unknwn.h`，而本文件只包含 `<windows.h>`：若使用者定义了 `WIN32_LEAN_AND_MEAN`（本项目其它编译单元常见做法），windows.h 不会引入 ole2/objbase，`STDMETHOD` 与 `interface` 宏都会未定义，导致随包含顺序不同而随机编译失败。建议显式包含依赖头，避免隐式依赖 windows.h 的默认包含集合。

**现有代码**

```c
#include "IBootstrapperEngine.h"
```

**改进建议**

```c
#include <objbase.h>

#include "IBootstrapperEngine.h"
```

#### 8. `tools/wix314/sdk/inc/IBootstrapperBAFunction.h:17-21` · 低 / 可维护性

> 文件同时暴露了 `extern "C"` 的保护和 C++ 专有语法（纯虚函数 `= 0`、`interface` 宏），即名义上兼容 C 但实际只能被 C++ 编译单元包含；若真有 C 端包含该头会直接编译失败。建议把接口声明也纳入 `#ifdef __cplusplus` 保护（或显式注明本头文件仅支持 C++），使意图与实现一致。

**现有代码**

```c
#ifdef __cplusplus
extern "C" {
#endif

typedef HRESULT (WINAPI *PFN_BOOTSTRAPPER_BA_FUNCTION_CREATE)(
```

**改进建议**

```c
#ifdef __cplusplus
extern "C" {
#endif

typedef HRESULT (WINAPI *PFN_BOOTSTRAPPER_BA_FUNCTION_CREATE)(
```

#### 9. `tools/wix314/sdk/inc/IBootstrapperBAFunction.h:24-25` · 中 / 缺陷

> Create 回调缺少失败时的输出参数契约：`ppBAFunction` 仅标注 `__out`，未约定失败（非 S_OK）时必须置为 NULL，调用方很容易在 HRESULT 判定不严格时读取未初始化指针而崩溃；另外 `pEngine`/`hModule` 也只是 `__in` 标注，没有说明传 NULL 时是否必须返回 `E_POINTER`/`E_INVALIDARG`。建议改用 `__deref_out` 并在注释中明确：进入函数时先将 `*ppBAFunction` 置 NULL，参数非法时返回 `E_POINTER`。

**现有代码**

```c
    __out IBootstrapperBAFunction** ppBAFunction
    );
```

**改进建议**

```c
    __deref_out IBootstrapperBAFunction** ppBAFunction
    );
```

#### 10. `tools/wix314/sdk/inc/aclutil.h:8-9` · 高 / 缺陷

> 释放宏存在三个经典缺陷：1) 宏体没有 do{...}while(0) 包裹，在 `if (cond) ReleaseSid(p); else ...` 这类上下文中会因宏内裸 `if` 造成 dangling-else，语义被静默改变；2) 参数被求值两次（`if (x)` 一次、`AclFreeSid(x)` 一次），若传入带副作用的表达式（如 `ReleaseSid(p++)`、`ReleaseSid(Next())`）会重复求值；3) `ReleaseSid` 释放后不置 NULL，同一个指针被释放两次即 double-free / use-after-free（`AclFreeSid` 内部若对非 NULL 指针调用 LocalFree 不会做空指针保护）。建议统一用 do-while + 局部临时变量做单次求值，并统一置 NULL 以避免调用方悬垂指针。

**现有代码**

```c
#define ReleaseSid(x) if (x) { AclFreeSid(x); }
#define ReleaseNullSid(x) if (x) { AclFreeSid(x); x = NULL; }
```

**改进建议**

```c
#define ReleaseSid(x) do { PSID __psidToRelease = (x); if (__psidToRelease) { AclFreeSid(__psidToRelease); (x) = NULL; } } while (0)
#define ReleaseNullSid(x) ReleaseSid(x)
```

#### 11. `tools/wix314/sdk/inc/aclutil.h:24-26` · 中 / 缺陷

> `nSubAuthorityCount` 为 BYTE，`nSubAuthority` 固定长度为 8，但头文件没有给出任何上限约束或断言说明。实现方（aclutil.cpp）在用这两个字段拼装 SID 时会以 count 作为循环上界，若调用方传入 count>8（BYTE 最大 255），将越界读 `nSubAuthority[]` 并构造出畸形 SID，甚至越界写。同时 Windows 的 `SID_MAX_SUB_AUTHORITIES` 为 15，8 这个上界也会静默截断合法的长 SID（如某些服务/域 SID）。建议定义显式上限宏（如 `#define ACL_MAX_SUB_AUTHORITY 8`）并在注释中明确契约「count 必须 ≤ 8」，便于实现与调用方统一校验。

**现有代码**

```c
    SID_IDENTIFIER_AUTHORITY sia;  // used if pwzAccountName is NULL
    BYTE nSubAuthorityCount;
    DWORD nSubAuthority[8];
```

**改进建议**

```c
    SID_IDENTIFIER_AUTHORITY sia;  // used if pwzAccountName is NULL
    BYTE nSubAuthorityCount;       // must be <= ACL_MAX_SUB_AUTHORITY
    DWORD nSubAuthority[ACL_MAX_SUB_AUTHORITY];
```

#### 12. `tools/wix314/sdk/inc/aclutil.h:58-62` · 中 / 文档

> 输出参数的所有权契约缺失：`AclGetAccountSid`/`AclGetWellKnownSid` 返回 PSID、`AclCreateDacl`/`AclAddToDacl`/`AclMergeDacls` 返回 ACL*、`AclCreateSecurityDescriptor*` 返回 SECURITY_DESCRIPTOR*、本函数与 `AclGetAccountSidStringEx` 返回 LPWSTR，但头文件中没有声明各自必须用哪个函数释放（`AclFreeSid` / `AclFreeDacl` / `AclFreeSecurityDescriptor` / `MemFree` 还是 `LocalFree`/`CoTaskMemFree`）。调用方极易混用系统释放函数导致堆损坏或泄漏（例如把 `AclGetWellKnownSid` 的结果交给 `LocalFree`）。建议在每个 `__deref_out*` 参数旁补注释说明分配方式与对应释放函数。

**现有代码**

```c
HRESULT DAPI AclGetAccountSidString(
    __in_z LPCWSTR wzSystem,
    __in_z LPCWSTR wzAccount,
    __deref_out_z LPWSTR* ppwzSid
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 13. `tools/wix314/sdk/inc/aclutil.h:98-100` · 中 / 安全

> 该接口把 `wzSddlFormat` 标注为 `__format_string` 并支持变参，属于典型格式化字符串风险点：SAL 注解只对编译期字面量生效，若调用方把外部可控字符串（如安装包中用户可编辑的 ACL 描述、命令行输入）直接当作格式串传入，`%n`/`%s` 会造成崩溃或内存写。头文件未提示该约束，建议在注释中明确「wzSddlFormat 必须是常量格式串，不可传入不可信输入；可变内容须作为参数传入并用 %s 占位」，同时提醒调用方 `%s` 参数需为 `wchar_t*`。

**现有代码**

```c
HRESULT __cdecl AclCreateSecurityDescriptorFromString(
    __deref_out SECURITY_DESCRIPTOR** ppsd,
    __in_z __format_string LPCWSTR wzSddlFormat,
```

**改进建议**

```c
// NOTE: wzSddlFormat must be a compile-time literal; never pass untrusted input as the format string.
HRESULT __cdecl AclCreateSecurityDescriptorFromString(
    __deref_out SECURITY_DESCRIPTOR** ppsd,
    __in_z __format_string LPCWSTR wzSddlFormat,
```

#### 14. `tools/wix314/sdk/inc/aclutil.h:84-85` · 低 / 可维护性

> 同一族接口的 SAL/const 注解不一致，易让调用方误判契约：1) `AclGetAccountSid` 的 wzSystem 是 `__in_opt`，而 `AclGetAccountSidString` 的 wzSystem 却是 `__in_z`（非可选），两者行为应一致；2) `AclCreateDaclOld` 和 `AclCreateSecurityDescriptor` 的输入数组 `paa` 未加 const，而 `AclAddToDacl` 用了 `const ACL_ACE[]`，输入型参数应统一 const；3) 输出参数命名 `ppwzSid` 与 `psczSid` 混用，`AclAddToDacl` 的 `cDeny`/`cAllow` 还缺少 `__in` 注解。建议统一注解风格，减少静态分析误报与误用。

**现有代码**

```c
HRESULT DAPI AclCreateDaclOld(
    __in_ecount(cAclAccesses) ACL_ACCESS* paa,
```

**改进建议**

```c
HRESULT DAPI AclCreateDaclOld(
    __in_ecount(cAclAccesses) const ACL_ACCESS* paa,
```

#### 15. `tools/wix314/sdk/inc/apuputil.h:9-10` · 高 / 缺陷

> 这两个释放宏存在两个问题：1) 宏体是裸 `if`，没有用 `do { } while (0)` 包裹，在 `if (cond) ReleaseApupChain(p); else ...` 这类不带花括号的用法中，`else` 会被错误地绑定到宏内部的 `if (p)` 上（dangling else），导致控制流被静默改变；同时 `p` 被多次求值，若传入带副作用的表达式（如 `ReleaseApupChain(pArr[i++])`）会错误自增甚至越界。2) 与项目约定不一致：同目录 `atomutil.h` 中 `ReleaseAtomFeed` 只释放、`ReleaseNullAtomFeed` 才置空，这里两个宏语义完全相同，调用方按惯例使用 `ReleaseApupChain` 时会意外把指针置空（与其它 Release* 宏行为不一致），也容易误以为是重复释放语义。建议拆分为“只释放”和“释放并置空”两个语义，并消除裸 if（如需保持项目宏风格，至少应修正语义并保证单次求值）。

**现有代码**

```c
#define ReleaseApupChain(p) if (p) { ApupFreeChain(p); p = NULL; }
#define ReleaseNullApupChain(p) if (p) { ApupFreeChain(p); p = NULL; }
```

**改进建议**

```c
#define ReleaseApupChain(p) if (p) { ApupFreeChain(p); }
#define ReleaseNullApupChain(p) if (p) { ApupFreeChain(p); p = NULL; }
```

#### 16. `tools/wix314/sdk/inc/apuputil.h:13` · 中 / 缺陷

> 该头文件同时支持 C 编译（仅在 `__cplusplus` 下加 `extern "C"`），而 C 语言中文件作用域的 `const` 变量默认是外部链接，多个 .c 文件包含本头文件时会产生重复符号/链接错误；C++ 下虽然是内部链接，但也会在每个 TU 生成一份副本。建议改为 `static const`，或改为 `extern` 声明 + 单独一处定义，或直接用 `#define`。

**现有代码**

```c
const LPCWSTR APPLICATION_SYNDICATION_NAMESPACE = L"http://appsyndication.org/2006/appsyn";
```

**改进建议**

```c
static const LPCWSTR APPLICATION_SYNDICATION_NAMESPACE = L"http://appsyndication.org/2006/appsyn";
```

#### 17. `tools/wix314/sdk/inc/apuputil.h:74-78` · 中 / 文档

> 接口的内存所有权约定缺失：`ApupAllocChainFromAtom` / `ApupFilterChain` 返回的链包含多层嵌套分配（`rgEntries`、`rgEnclosures`、`wzUrl`/`wzLocalName` 等字符串、`rgbDigest` 字节缓冲），头文件未说明这些内存由谁分配、由谁释放、是否深拷贝。特别需要明确：`ApupFilterChain` 是否深拷贝 enclosure 的 `rgbDigest`；过滤链/源链能否都交给 `ApupFreeChain` 释放（否则要么泄漏、要么 double-free），以及 `ApupFreeChain` 是否允许传入 NULL（当前签名为 `__in` 且返回 void，建议明确容忍 NULL）。建议在此处补充注释约定所有权与 NULL/失败时的行为。另外 `pChain` 是只读输入，建议加 `__in const` 以便静态分析与调用方正确使用。

**现有代码**

```c
HRESULT DAPI ApupFilterChain(
    __in APPLICATION_UPDATE_CHAIN* pChain,
    __in DWORD64 dw64Version,
    __out APPLICATION_UPDATE_CHAIN** ppFilteredChain
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 18. `tools/wix314/sdk/inc/apuputil.h:30-32` · 中 / 安全

> 摘要信息把算法与摘要值分开存储，且 `APUP_HASH_ALGORITHM` 的首个枚举值为 `UNKNOWN`（数值 0），意味着结构体被零初始化/解析失败时默认就是未知算法。接口层未约定按算法校验摘要长度（MD5=16、SHA1=20、SHA256=32 字节），调用方很容易在 `digestAlgorithm == UNKNOWN` 或 `cbDigest` 长度不符时跳过/错误地执行完整性校验。建议在枚举或该字段处补充注释，明确：解析时必须拒绝 `UNKNOWN`，`rgbDigest` 长度必须与算法匹配，`cbDigest` 与算法不一致时整条 entry 视为无效。

**现有代码**

```c
    BYTE* rgbDigest;
    DWORD cbDigest;
    APUP_HASH_ALGORITHM digestAlgorithm;
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 19. `tools/wix314/sdk/inc/IBootstrapperEngine.h:5` · 中 / 缺陷

> 宏 `IDERROR` 的值为未加括号的 `-1`，属于典型的宏展开陷阱：`-IDERROR` 会被展开为 `--1`（`--` 是递减运算符 token）导致编译失败，`IDERROR*2` 之类表达式也依赖上下文。建议改为 `#define IDERROR (-1)`。另外 `IDERROR/IDNOACTION/IDRESTART/IDSUSPEND` 这类名字过于通用，且 `IDNOACTION` 已在 tools/wix314/sdk/inc/wiutil.h 中重复定义，公共 SDK 头文件里建议加前缀（如 `WIX_IDERROR`）或改用 enum 常量以避免全局命名空间污染。

**现有代码**

```c
#define IDERROR -1
```

**改进建议**

```c
#define IDERROR (-1)
```

#### 20. `tools/wix314/sdk/inc/IBootstrapperEngine.h:12` · 中 / 可维护性

> 该常量没有 `#ifndef` 保护且以 `static const` 形式定义在公共头文件中：1) 每个包含此头的翻译单元都会生成一份内部链接副本，C 编译器下还会产生未使用变量告警（`/W4 /WX` 会直接报错）；2) 在 C 语言中 `static const` 不是常量表达式，无法用于 `case` 标签或数组维度；3) 若另一个头文件也定义了同名常量会直接发生重复定义冲突。建议加 `#ifndef E_SUSPECTED_AV_INTERFERENCE` 保护，并改用宏或 `constexpr`（C++）/`enum`。

**现有代码**

```c
static const HRESULT E_SUSPECTED_AV_INTERFERENCE = MAKE_HRESULT(SEVERITY_ERROR, FACILITY_WIX, 2000);
```

**改进建议**

```c
#ifndef E_SUSPECTED_AV_INTERFERENCE
#define E_SUSPECTED_AV_INTERFERENCE MAKE_HRESULT(SEVERITY_ERROR, FACILITY_WIX, 2000)
#endif
```

#### 21. `tools/wix314/sdk/inc/IBootstrapperEngine.h:21-23` · 中 / 可维护性

> 按注释所述，多处代码依赖 `BOOTSTRAPPER_ACTION` 的相对大小比较，而枚举目前完全依赖隐式递增值：一旦有人在中间插入新值或调整顺序，比较逻辑即静默失效且编译器不会报错；这些值还可能被写入日志/序列化或跨进程传递。建议为每个枚举量显式指定固定的数值，并在末尾补 `BOOTSTRAPPER_ACTION_MAX`（或 COUNT）作为边界哨兵，同时为 < / > 比较提供带断言的辅助函数。另外注意末尾枚举量后的尾逗号在 C++03/C89 严格模式下不合法，若头文件需被 C 或旧标准编译器包含会编译失败。

**现有代码**

```c
enum BOOTSTRAPPER_ACTION
{
    BOOTSTRAPPER_ACTION_UNKNOWN,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 22. `tools/wix314/sdk/inc/IBootstrapperEngine.h:117` · 中 / 文档

> `GetVariableString`（以及下方 `FormatString`/`EscapeString`）的缓冲区契约只靠 SAL 表达，缺少文字说明：当 `*pcchValue == 0` 且 `wzValue == NULL` 时是否用于查询所需长度、`*pcchValue` 是输入容量还是输出所需长度、缓冲区不足时的返回码（如 `E_MOREDATA`/`ERROR_MORE_DATA`）、以及是否保证空终止，都没有约定。调用方很容易按“传入容量即成功”的方式误用导致截断或越界读取。建议在接口声明处补充上述语义注释，并明确 `*pcchValue` 为 in/out 且失败时回填所需长度（含结尾 NUL）。

**现有代码**

```c
        __out_ecount_opt(*pcchValue) LPWSTR wzValue,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 23. `tools/wix314/sdk/inc/IBootstrapperEngine.h:166` · 中 / 安全

> `SetUpdate` 的哈希参数缺少约束：`rgbHash` 声明为非 const 的 `BYTE*`（虽标了 `__in_bcount_opt`，但接口语义上是只读输入，应为 `const BYTE*`，否则实现/调用双方容易误改缓冲区）；同时 `cbHash` 与 `hashType` 的长度对应关系（如 SHA1 固定 20 字节）未在 SAL 或注释中体现，允许出现 hashType 非 NONE 但 rgbHash 为 NULL 或长度不匹配的组合，实现若未严格校验就可能跳过哈希验证造成校验绕过。建议改为 `const BYTE*` 并在此处注释说明各 hashType 要求的固定长度及不满足时应返回的错误码。

**现有代码**

```c
        __in_bcount_opt(cbHash) BYTE* rgbHash,
```

**改进建议**

```c
        __in_bcount_opt(cbHash) const BYTE* rgbHash,
```

#### 24. `tools/wix314/sdk/inc/IBootstrapperEngine.h:202` · 中 / 缺陷

> 在纯虚 COM 接口方法上写默认实参是有害且易误导的：默认实参在编译期按静态类型绑定，经 vtable 或不同类型的接口指针调用时会被忽略，不同语言/跨进程封送（IDL/marshal）也不会携带默认值；同时它与同文件中 `Elevate`/`Apply`（同为 `__in_opt HWND hwndParent` 但无默认值）风格不一致，并且默认实参属于 C++ 语法，会导致该头文件无法被 C 代码包含。建议去掉默认值，与其它方法保持一致。

**现有代码**

```c
        __in_opt HWND hwndParent = NULL
```

**改进建议**

```c
        __in_opt HWND hwndParent
```

#### 25. `tools/wix314/sdk/inc/IBootstrapperEngine.h:181` · 中 / 安全

> `SetDownloadSource` 以明文 `LPCWSTR` 传递下载凭据（用户名/密码）：凭据会在调用进程与引擎进程间以明文封送，且很容易被写入详细日志（`Log`/`BOOTSTRAPPER_LOG_LEVEL_DEBUG` 打开时）或被任意第三方 UI 读取。建议在该声明处明确契约：凭据不得记录到日志、须在与 `wzUrl` 一致的可信（HTTPS）源上使用、并在用完后及时清零；同时说明 `wzUrl` 传入非预期主机时引擎是否允许携带凭据，避免凭据被转发到攻击者指定的地址。

**现有代码**

```c
        __in_z_opt LPCWSTR wzPassword
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 26. `tools/wix314/sdk/inc/apuputil.h:69-72` · 低 / 文档

> `ApupAllocChainFromAtom` 直接信任外部 Atom feed 的内容（URL、`wzLocalName`、`dw64Size`、`cEnclosures` 等）。头文件未约定安全契约：URL scheme 是否限制为 https、`wzLocalName` 是否只允许纯文件名以防路径穿越、`dw64Size`/`cEnclosures` 是否需限上限以防整数溢出或内存耗尽、单个 entry 的 `szEnclosures` 总和是否需与 `dw64TotalSize` 一致性校验。建议在此声明处补充注释，明确实现和调用方需对不可信 feed 做这些校验（或将校验责任明确交给调用方），否则上层容易直接使用未验证的数据执行下载/写入文件。

**现有代码**

```c
HRESULT DAPI ApupAllocChainFromAtom(
    __in ATOM_FEED* pFeed,
    __out APPLICATION_UPDATE_CHAIN** ppChain
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 27. `tools/wix314/sdk/inc/atomutil.h:140-142` · 高 / 缺陷

> SAL 注解错误且参数名不一致：`ATOM_FEED` 中并不存在 `cItems` 成员（只有 `cEntries`/`cAuthors`/`cCategories`/`cLinks`），`__in_xcount(pFeed->cItems)` 会让静态分析（/analyze）报错或直接失效；同时参数名是 `pFEED`，注解里引用的 `pFeed` 与声明不匹配。另外 `AtomFreeFeed` 释放的是单个 feed 结构体（其内部数组才按 count 释放），用 xcount 表达数组计数语义本身就是错的。

**现有代码**

```c
void DAPI AtomFreeFeed(
    __in_xcount(pFeed->cItems) ATOM_FEED *pFEED
    );
```

**改进建议**

```c
void DAPI AtomFreeFeed(
    __in ATOM_FEED *pFeed
    );
```

#### 28. `tools/wix314/sdk/inc/atomutil.h:9-10` · 中 / 缺陷

> 释放宏存在三个问题：1) 未用 `do { ... } while (0)` 包裹，`if (x) ReleaseAtomFeed(p); else ...` 会因宏展开的 if 破坏 else 配对；2) 参数 `p` 在条件与调用中被求值两次，若传入带副作用的表达式（如 `ReleaseAtomFeed(pf = GetFeed())`）会重复执行；3) `ReleaseAtomFeed` 释放后不置空，调用方极易继续使用悬垂指针，与 `ReleaseNullAtomFeed` 语义不一致。建议统一包裹并避免重复求值。

**现有代码**

```c
#define ReleaseAtomFeed(p) if (p) { AtomFreeFeed(p); }
#define ReleaseNullAtomFeed(p) if (p) { AtomFreeFeed(p); p = NULL; }
```

**改进建议**

```c
#define ReleaseAtomFeed(p) if (p) { AtomFreeFeed(p); }
#define ReleaseNullAtomFeed(p) do { if (p) { AtomFreeFeed(p); (p) = NULL; } } while (0)
```

#### 29. `tools/wix314/sdk/inc/atomutil.h:86-89` · 中 / 缺陷

> `pixn` 的所有权语义未在接口中约定，存在悬挂指针/重复释放风险：`AtomParseFromDocument` 接受调用方的 `IXMLDOMDocument*`，若返回的 feed/entry 只是直接保存其子节点指针（未 AddRef），调用方随后 Release 文档即导致 `pixn` 悬挂；反之若 AtomFreeFeed 去 Release 这些节点，则可能重复释放调用方的文档。建议在头文件注释中明确“是否 AddRef、由谁释放、调用方能否在解析后立即释放文档”。

**现有代码**

```c
    DWORD cLinks;
    ATOM_LINK* rgLinks;

    IXMLDOMNode* pixn;
```

**改进建议**

```c
    DWORD cLinks;
    ATOM_LINK* rgLinks;

    // 由 AtomParseFromXxx 内部 AddRef，AtomFreeFeed 负责 Release；调用方可在解析后释放自己持有的文档。
    IXMLDOMNode* pixn;
```

#### 30. `tools/wix314/sdk/inc/atomutil.h:125-128` · 中 / 安全

> 解析接口未对输入规模与解析器安全选项做任何约定：`AtomParseFromString`/`AtomParseFromFile` 无最大长度/最大节点数限制，也无法让调用方指定是否禁用 DTD 与外部实体，若实现侧使用 MSXML 默认配置，则存在 XXE 与实体膨胀（billion laughs）导致的拒绝服务风险。建议补充明确的契约说明（是否禁用 DTD/外部实体、输入上限），并在参数上给出长度约束（如 `__in_z` 之外再加 `__in_ecount` 或显式长度参数）。

**现有代码**

```c
HRESULT DAPI AtomParseFromString(
    __in_z LPCWSTR wzAtomString,
    __out ATOM_FEED **ppFeed
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 31. `tools/wix314/sdk/inc/atomutil.h:119-120` · 低 / 其他

> `AtomInitialize`/`AtomUninitialize` 成对操作的是进程级全局状态（通常是 MSXML/COM 与内部缓存），但接口未说明是否可重入、是否引用计数、多线程并发调用是否安全、重复 Uninitialize 的行为，调用方容易在使用中提前反初始化或并发初始化。建议补充线程安全与配对调用（引用计数）的契约说明。

**现有代码**

```c
HRESULT DAPI AtomInitialize(
    );
```

**改进建议**

```c
// 说明：进程级全局初始化，内部引用计数；多线程可安全调用，最后一个 AtomUninitialize 之后才能再次 AtomInitialize。
HRESULT DAPI AtomInitialize(
    );
```

#### 32. `tools/wix314/sdk/inc/atomutil.h:13-15` · 低 / 可维护性

> 头文件类型不自包含：结构体只定义了 tag（`struct ATOM_FEED`）而没有 typedef，内部互相引用也直接写 `ATOM_UNKNOWN_ATTRIBUTE*`、函数原型直接用 `ATOM_FEED*`——这只有在 C++ 下合法；同时 `LPWSTR`/`FILETIME`/`DWORD64`/`IXMLDOMNode`/`HRESULT`/`DAPI` 均依赖使用方先包含 windows.h、msxml 与 dutil.h。虽然与 rssutil.h 等现有头一致，但建议至少在文件头加注释说明所需的包含顺序，或补充 `typedef struct ATOM_FEED ATOM_FEED;` 之类的前置声明，避免被以 C 方式包含时直接编译失败。

**现有代码**

```c
struct ATOM_UNKNOWN_ATTRIBUTE
{
    LPWSTR wzNamespace;
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 33. `tools/wix314/sdk/inc/IBootstrapperApplication.h:1` · 中 / 缺陷

> 头文件不自包含：本文件未包含任何头文件/前置声明，却直接使用了 HRESULT / LPWSTR / HWND / BOOL / DWORD / UINT（windows.h）、INSTALLMESSAGE（msiquery.h）、DECLARE_INTERFACE_IID_ 与 IUnknown，以及 IBootstrapperEngine.h 中定义的 BOOTSTRAPPER_ACTION、BOOTSTRAPPER_PACKAGE_STATE、BOOTSTRAPPER_REQUEST_STATE、BOOTSTRAPPER_FEATURE_STATE、BOOTSTRAPPER_ACTION_STATE、IDNOACTION/IDDOWNLOAD/IDRESTART/IDRELOAD_BOOTSTRAPPER 等。目前它只有在使用者恰好先包含 IBootstrapperEngine.h 与 windows.h 时才能编译（如 BalBaseBootstrapperApplication.h 第 3-7 行的包含顺序），包含顺序一变即编译失败。建议在本文件顶部补齐依赖，让头文件可独立使用。

**现有代码**

```c
#pragma once
```

**改进建议**

```c
#pragma once

#include <windows.h>
#include <msiquery.h>

#include "IBootstrapperEngine.h"
```

#### 34. `tools/wix314/sdk/inc/IBootstrapperApplication.h:5-7` · 高 / 可维护性

> 这些枚举是与外部 BA/引擎二进制（以及已发布的 SDK）共享的 ABI 契约，但成员没有显式赋值。任何人日后在枚举中间插入/调整成员（例如补一个 UNKNOWN 或错误值），后续所有枚举值的数值都会平移，导致旧版 BA 与新引擎（或反之）对状态码的理解错位且不会产生编译错误，属于静默的不兼容。建议为每个枚举显式编号，并对关键枚举加静态断言/注释固定取值。

**现有代码**

```c
enum BOOTSTRAPPER_DISPLAY
{
    BOOTSTRAPPER_DISPLAY_UNKNOWN,
```

**改进建议**

```c
enum BOOTSTRAPPER_DISPLAY
{
    BOOTSTRAPPER_DISPLAY_UNKNOWN = 0,
    BOOTSTRAPPER_DISPLAY_EMBEDDED = 1,
    BOOTSTRAPPER_DISPLAY_NONE = 2,
    BOOTSTRAPPER_DISPLAY_PASSIVE = 3,
    BOOTSTRAPPER_DISPLAY_FULL = 4,
```

#### 35. `tools/wix314/sdk/inc/IBootstrapperApplication.h:94` · 中 / 缺陷

> BOOTSTRAPPER_COMMAND 是跨 DLL 边界交给 BA 的输入结构，但这里是可写的 LPWSTR：BA 若修改/释放 wzCommandLine（以及下面的 wzLayoutDirectory）会破坏引擎内存。同时未注明这两个指针的所有权与生命周期（仅在 PFN_BOOTSTRAPPER_APPLICATION_CREATE 回调期间有效、BA 必须自行拷贝），也未注明可能为 NULL。建议改为 LPCWSTR 并补充所有权/生命周期/可空性说明；若该结构需要长期兼容，还应考虑加版本/大小字段以支持后续扩展。

**现有代码**

```c
    LPWSTR wzCommandLine;
```

**改进建议**

```c
    // 只读，生命周期仅在 PFN_BOOTSTRAPPER_APPLICATION_CREATE 回调期间有效，BA 需自行拷贝。
    LPCWSTR wzCommandLine;
```

#### 36. `tools/wix314/sdk/inc/IBootstrapperApplication.h:290` · 低 / 文档

> 注释里的函数名写错了（复制粘贴遗留）：这段说的是 OnDetectComplete，却写成了 OnDetectPackageComplete，容易让 BA 实现者误以为两个回调语义相同而漏实现/错实现。

**现有代码**

```c
    // OnDetectPackageComplete - called after the engine completes detection.
```

**改进建议**

```c
    // OnDetectComplete - called after the engine completes detection.
```

#### 37. `tools/wix314/sdk/inc/IBootstrapperApplication.h:601` · 低 / 文档

> 同样的问题：该注释挂在 OnExecutePackageBegin 上，但写成了 OnExecuteBegin，与前面真正的 OnExecuteBegin（执行整个 plan）混淆，且本回调的 fExecute 参数含义（回滚时为 FALSE）也没有说明。

**现有代码**

```c
    // OnExecuteBegin - called when the engine begins executing a package.
```

**改进建议**

```c
    // OnExecutePackageBegin - called when the engine begins executing a package.
    //
    // Parameters:
    //  fExecute is FALSE when the package is being executed for rollback/uninstall.
```

#### 38. `tools/wix314/sdk/inc/IBootstrapperApplication.h:734` · 中 / 文档

> OnLaunchApprovedExeBegin 返回 int，但唯独它没有像其他 On* 回调那样约定返回值语义（IDCANCEL 是否阻止启动、IDNOACTION 是否继续），实现者只能靠猜；同时缺少“Begin 与 Complete 成对出现、Complete 在失败时仍会回调”的说明，容易写出提前返回后状态不一致的 BA。

**现有代码**

```c
    STDMETHOD_(int, OnLaunchApprovedExeBegin)() = 0;
```

**改进建议**

```c
    // Return:
    //  IDCANCEL instructs the engine to abort launching the preapproved executable.
    //
    //  IDNOACTION instructs the engine to continue. OnLaunchApprovedExeComplete is
    //             always called afterwards, even when the launch fails.
    STDMETHOD_(int, OnLaunchApprovedExeBegin)() = 0;
```

#### 39. `tools/wix314/sdk/inc/IBootstrapperApplication.h:108` · 中 / 文档

> 该 COM 接口没有任何关于调用线程/COM apartment/重入的契约说明。实际上这些回调由引擎线程串行调用，且 OnResolveSource、OnElevate 等回调内 BA 还可以反过来调用 IBootstrapperEngine（如 SetLocalSource/SetDownloadSource），属于重入场景。缺少约定时实现方很容易在回调里阻塞 UI 线程或持有锁回调引擎，产生死锁/竞态；另外接口新增方法只能追加在末尾并升级 IID，这一点也应在接口处写明。

**现有代码**

```c
DECLARE_INTERFACE_IID_(IBootstrapperApplication, IUnknown, "53C31D56-49C0-426B-AB06-099D717C67FE")
```

**改进建议**

```c
// All callbacks are invoked serially on the engine's thread. A callback may call back
// into IBootstrapperEngine (e.g. SetLocalSource from OnResolveSource), so implementations
// must not hold locks or block on the UI thread while inside a callback.
//
// This is a binary contract: new methods may only be appended and changing the vtable
// requires a new interface (and IID).
DECLARE_INTERFACE_IID_(IBootstrapperApplication, IUnknown, "53C31D56-49C0-426B-AB06-099D717C67FE")
```

#### 40. `tools/wix314/sdk/inc/IBootstrapperApplication.h:749` · 中 / 文档

> 创建/销毁回调缺少所有权与引用计数约定：pEngine 在回调返回后是否继续有效、BA 是否需要 AddRef、ppApplication 是否需返回已 AddRef 的引用、由谁 Release（引擎还是 Destroy）、Destroy 在哪个线程/时机被调用、失败时 ppApplication 是否必须置 NULL，都没有说明。这类信息缺失极易导致引擎提前释放（回调内使用了已失效的 pEngine）或 BA 对象泄漏。

**现有代码**

```c
extern "C" typedef HRESULT (WINAPI *PFN_BOOTSTRAPPER_APPLICATION_CREATE)(
```

**改进建议**

```c
// The engine retains ownership of pEngine and it remains valid for the lifetime of the BA.
// The BA must return its own reference in *ppApplication (addref'd); the engine releases
// it before calling PFN_BOOTSTRAPPER_APPLICATION_DESTROY.
// pCommand and the strings it points to are only valid during this call.
extern "C" typedef HRESULT (WINAPI *PFN_BOOTSTRAPPER_APPLICATION_CREATE)(
```

#### 41. `tools/wix314/sdk/inc/balcondition.h:9-13` · 中 / 文档

> 结构体成员的内存所有权契约缺失，容易导致调用方误判。`sczCondition`/`sczMessage` 是由解析函数 stralloc 出来的堆字符串（需 CoTaskMem/StrFree 释放），而 `rgConditions` 是堆数组，二者释放方式不同；头文件既未说明“谁分配、谁释放”，也未说明 `BalConditionsUninitialize` 之后字段是否被置零。建议补充注释明确：1) 两个 LPWSTR 由库分配、由 Uninitialize 释放，调用方不得自行释放或替换；2) Uninitialize 会深释放数组与字符串并将结构清零，可安全重复调用；3) 结构体必须零初始化后再传入解析函数。

**现有代码**

```c
typedef struct _BAL_CONDITION
{
    LPWSTR sczCondition;
    LPWSTR sczMessage;
} BAL_CONDITION;
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 42. `tools/wix314/sdk/inc/balcondition.h:27-28` · 中 / 缺陷

> SAL 注解与实际语义不符：该函数会把解析结果写入 `pConditions`（填充 rgConditions/cConditions），参数应为 `__inout`（或 `__out`）而非 `__in`。`__in` 会让静态分析认为调用方只需提供只读输入，从而漏掉“结构必须先零初始化”的前置条件，也无法检测未初始化内存被追加写入的问题。同时建议在注释中明确失败语义：解析中途失败时是否回滚已分配的条件、`cConditions` 与 `rgConditions` 是否保证一致（避免留下半成品数组导致后续 Uninitialize 越界或泄漏）。

**现有代码**

```c
DAPI_(HRESULT) BalConditionsParseFromXml(
    __in BAL_CONDITIONS* pConditions,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 43. `tools/wix314/sdk/inc/balcondition.h:42-43` · 中 / 缺陷

> 输出参数契约不严谨：1) `pfResult` 与 `psczMessage` 均用 `__out`/`__out_z_opt` 修饰，意味着“成功时必定写入”，但此函数内部需要解析条件表达式并调用引擎，存在早期失败路径（pCondition/pEngine 为空、表达式非法、引擎求值失败）；失败时这两个输出会保持调用方的未初始化值，调用方若在失败后读取 `*pfResult` 或释放 `*psczMessage` 就是未定义行为。建议改为 `__out_opt`/`__deref_opt_out_z` 并明确“失败时不修改输出”或“失败时置 NULL/FALSE”。2) `psczMessage` 是 `LPWSTR*`，注释只说 optional，未说明是新建分配字符串还是指向内部常量；若为前者必须写明由调用方负责释放（StrFree/CoTaskMemFree），否则必然泄漏。3) `pCondition` 本身不参与求值写入，应为 `__in const BAL_CONDITION*`，以便调用方在多线程下共享条件集。

**现有代码**

```c
    __out BOOL* pfResult,
    __out_z_opt LPWSTR* psczMessage
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 44. `tools/wix314/sdk/inc/balcondition.h:51-53` · 低 / 可维护性

> `BalConditionsUninitialize` 会修改并清零结构内容，参数语义是 `__inout` 而非 `__in`；用 `__in` 无法表达“调用后结构变为空”，也阻止了静态分析发现“Uninitialize 后再次 Evaluate/Uninitialize”这类生命周期错误。另外建议在注释中补一句并发/生命周期约束：条件集在解析完成后才可被 Evaluate 共享读取，Evaluate 与 Uninitialize 不可并发（Uninitialize 会释放另一线程正在求值的字符串），以免上层误用导致 use-after-free。

**现有代码**

```c
DAPI_(void) BalConditionsUninitialize(
    __in BAL_CONDITIONS* pConditions
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 45. `tools/wix314/sdk/inc/balretry.h:5-9` · 中 / 可维护性

> 该头文件未包含任何前置声明来源，却直接使用 DAPI_、DWORD、LPCWSTR、HRESULT 以及 SAL 注解 __in/__in_z_opt。同目录下的 balutil.h、wcautil.h 都会自行 `#include "dutil.h"`，本文件却依赖调用方先包含 windows.h/dutil.h，单独包含时会编译失败，也不利于按需使用。建议在 `extern "C"` 之前补上 `#include <windows.h>`（或 dutil.h）以保证自包含。

**现有代码**

```c
#ifdef __cplusplus
extern "C" {
#endif

typedef enum BALRETRY_TYPE
```

**改进建议**

```c
#ifdef __cplusplus
extern "C" {
#endif

typedef enum BALRETRY_TYPE
```

#### 46. `tools/wix314/sdk/inc/balretry.h:12-13` · 低 / 可维护性

> 枚举没有结束哨兵也没有显式值：type 参数标注为 __in 却无法校验合法性，调用方传入越界值（如未初始化变量强转）时会在实现里落到未定义分支。建议增加 BALRETRY_TYPE_MAX 之类的哨兵并显式赋值（`= 0`、`= 1`），便于参数校验和 ABI 稳定性。

**现有代码**

```c
    BALRETRY_TYPE_EXECUTE,
} BALRETRY_TYPE;
```

**改进建议**

```c
    BALRETRY_TYPE_EXECUTE = 1,
    BALRETRY_TYPE_MAX,
} BALRETRY_TYPE;
```

#### 47. `tools/wix314/sdk/inc/balretry.h:19-22` · 中 / 文档

> 接口围绕 Initialize/Uninitialize 建立的全局状态设计，但契约完全缺失：1) 重复 Initialize 是覆盖还是泄漏；2) 未 Initialize 即调用 StartPackage/ErrorOccurred/EndPackage 的行为；3) Uninitialize 后再次调用是否安全；4) dwTimeout 的单位与 dwMaxRetries 的含义（每个包独立计数还是全局计数）。这些都不明确，调用方极易误用并导致重试计数错乱或状态泄漏，建议在注释中显式写明。

**现有代码**

```c
DAPI_(void) BalRetryInitialize(
    __in DWORD dwMaxRetries,
    __in DWORD dwTimeout
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 48. `tools/wix314/sdk/inc/balretry.h:28` · 低 / 可维护性

> 声明为 `()` 而非 `(void)`：在 C 语言中空参数列表表示参数未指定（可传任意参数），与“无参数”语义不符，也不便于编译器检查。建议改为 `(void)`。

**现有代码**

```c
DAPI_(void) BalRetryUninitialize();
```

**改进建议**

```c
DAPI_(void) BalRetryUninitialize(void);
```

#### 49. `tools/wix314/sdk/inc/balretry.h:35-36` · 中 / 缺陷

> 注释明确说明该函数在重试时会“等待指定超时”，但返回 void、既无取消信号也无失败返回，也未说明是否可重入。若在 UI 线程或持锁线程/消息泵线程中调用，最长会阻塞 dwTimeout * dwMaxRetries 毫秒且无法中断（例如用户点击取消仍会卡住）。建议在文档中明确禁止在 UI 线程调用，或提供可传入取消回调/是否已取消的接口。

**现有代码**

```c
DAPI_(void) BalRetryStartPackage(
    __in BALRETRY_TYPE type,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 50. `tools/wix314/sdk/inc/balretry.h:42` · 低 / 文档

> 注释中的函数名拼写为 `BalRetryErrorOccured`，而实际声明是 `BalRetryErrorOccurred`，检索/文档生成时会对不上。

**现有代码**

```c
 BalRetryErrorOccured - call when an error occurs for the retry utility
```

**改进建议**

```c
 BalRetryErrorOccurred - call when an error occurs for the retry utility
```

#### 51. `tools/wix314/sdk/inc/balretry.h:45-47` · 中 / 缺陷

> 错误码类型不一致：记录错误时用 DWORD dwError，而判定是否重试时用 HRESULT hrError，同一重试上下文中的错误值需要调用方自行做 DWORD/HRESULT 转换（现有调用点就分别传 dwCode 与 hrExitCode），容易出现符号/成败判断偏差。建议统一为 HRESULT，或在注释中明确两者的映射与成功失败判定规则。

**现有代码**

```c
DAPI_(void) BalRetryErrorOccurred(
    __in_z_opt LPCWSTR wzPackageId,
    __in DWORD dwError
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 52. `tools/wix314/sdk/inc/balretry.h:54` · 中 / 可维护性

> 返回值契约不清：声明为 int，仅靠注释说明“返回 IDRETRY / IDNOACTION”，既没有枚举也没有常量定义，调用方需直接与 Win32 的消息框常量比较（现有调用点还混用 IDCANCEL 判断），拼错或误判时编译器不会报错。另外注释本身有笔误（“returns IDRETRY is a retry is recommended”）。建议定义明确的枚举/常量并在注释中列出全部可能返回值及调用方应如何处理。

**现有代码**

```c
DAPI_(int) BalRetryEndPackage(
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 53. `tools/wix314/sdk/inc/balretry.h:54-58` · 低 / 文档

> 三个阶段的标识参数（wzPackageId / wzPayloadId）均声明为 __in_z_opt（允许 NULL），但没有说明空值以及不同组合（仅包 ID / 包 ID+负载 ID / 仅负载 ID）如何映射到同一个重试上下文。例如 StartPackage 用 (id, NULL)、EndPackage 用 (id, payload) 时是否会命中同一条计数，NULL payload 是否代表“整个包”；语义不清会造成重试计数归属错误或永不重试。建议在文件头或每个接口注释中明确匹配规则。

**现有代码**

```c
DAPI_(int) BalRetryEndPackage(
    __in BALRETRY_TYPE type,
    __in_z_opt LPCWSTR wzPackageId,
    __in_z_opt LPCWSTR wzPayloadId,
    __in HRESULT hrError
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 54. `tools/wix314/sdk/inc/balinfo.h:6` · 中 / 缺陷

> 该头文件不是自包含的：文件中使用了 `LPWSTR`/`BOOL`/`HRESULT`/`DAPI_`/`__in`/`__out`（需 windows.h 或 dutil.h）、`IXMLDOMDocument`（需 msxml）、`BOOTSTRAPPER_ACTION_STATE`（定义于 IBooststrapperEngine.h）和 `BOOTSTRAPPER_RELATION_TYPE`（定义于 IBooststrapperApplication.h），但本文件没有 include 任何头文件。同目录下其它 SDK 头（如 balutil.h、BalBaseBootstrapperApplication.h、wcautil.h）均自带依赖 include，因此若使用方先包含 balinfo.h 会直接编译失败（未定义类型）。建议补齐依赖头。

**现有代码**

```c
extern "C" {
```

**改进建议**

```c
#include <windows.h>
#include <msxml6.h>

#include "dutil.h"
#include "IBootstrapperEngine.h"
#include "IBootstrapperApplication.h"

extern "C" {
```

#### 55. `tools/wix314/sdk/inc/balinfo.h:9-11` · 中 / 可维护性

> 这两个枚举属于公开 SDK ABI，但没有显式赋值：后续任何插入/重排成员都会静默改变已有常量值并使二进制不兼容；同时对 `BAL_INFO_CACHE_TYPE_NO` 这类“0 值即默认行为”的语义也不直观（结构体零初始化后 cacheType 即为 NO）。建议显式写出数值，新增值只能追加在末尾。

**现有代码**

```c
typedef enum BAL_INFO_PACKAGE_TYPE
{
    BAL_INFO_PACKAGE_TYPE_UNKNOWN,
```

**改进建议**

```c
typedef enum BAL_INFO_PACKAGE_TYPE
{
    BAL_INFO_PACKAGE_TYPE_UNKNOWN = 0,
```

#### 56. `tools/wix314/sdk/inc/balinfo.h:70` · 中 / 缺陷

> `pBundle` 实际是输出参数（函数把解析结果写入结构体），标注为 `__in` 会让静态分析（PREFast/SAL）误判其内容在调用前被读取，也会误导调用方传入已初始化数据。建议改为 `__out`（若实现按字段增量填充则用 `__inout`），并在注释中说明：调用方负责传入零初始化结构体，解析失败时的已分配字段由谁清理（建议实现内部失败即回滚，或明确要求调用方失败后仍调用 BalInfoUninitialize）。

**现有代码**

```c
    __in BAL_INFO_BUNDLE* pBundle,
```

**改进建议**

```c
    __out BAL_INFO_BUNDLE* pBundle,
```

#### 57. `tools/wix314/sdk/inc/balinfo.h:65` · 中 / 文档

> 接口契约未定义清楚：注释只说“载入 bundle/package 信息”，没有说明 XML 装载选项。UX 清单来自外部 bundle，若实现使用 MSXML 默认设置解析，存在 DTD/外部实体（XXE）与超大实体膨胀风险。建议在注释中明确要求禁用 DTD/外部实体解析（如 `ProhibitDtd = VARIANT_TRUE`、`ResolveExternals = VARIANT_FALSE`、`setProperty` 关闭 `AllowXsltScript` 等），以便实现方与后续维护者有据可依。

**现有代码**

```c
 BalInfoParseFromXml - loads the bundle and package info from the UX
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 58. `tools/wix314/sdk/inc/balinfo.h:94` · 中 / 缺陷

> 查找接口的出参契约缺失：未说明 `pPackages`/`wzId`/`ppPackage` 为 NULL 时如何处理，也未说明“未找到”时 `ppPackage` 是否被置 NULL、返回 S_OK 还是 E_NOTFOUND。若实现只在找到时赋值，调用方在只校验 S_OK 的情况下可能解引用未初始化指针。建议在注释中明确：入参不得为 NULL；未找到时返回 E_NOTFOUND 且 `*ppPackage = NULL`。

**现有代码**

```c
    __out BAL_INFO_PACKAGE** ppPackage
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 59. `tools/wix314/sdk/inc/balinfo.h:50-51` · 低 / 性能

> `BAL_INFO_PACKAGES` 只有指针与计数、没有容量字段：`BalInfoAddRelatedBundleAsPackage` 每次追加都必须 realloc（失败时还需保证原数组不被泄漏/悬垂），批量添加关联 bundle 时整体退化为 O(n²) 且频繁搬移可能使已返回的 `BAL_INFO_PACKAGE*` 失效。建议增加内部容量字段（或提供预留/批量追加接口），并在此处注明：追加后此前取得的元素指针可能失效、数组及其中字符串由 BalInfoUninitialize 统一释放。

**现有代码**

```c
    BAL_INFO_PACKAGE* rgPackages;
    DWORD cPackages;
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 60. `tools/wix314/sdk/inc/cabutil.h:19` · 高 / 缺陷

> SEEK 回调的偏移类型与上层 API 不一致：CabExtract/CabEnumerate 使用 DWORD64 dw64EmbeddedOffset（支持从宿主文件任意位置定位嵌入 CAB），但这里 dwMove 只有 32 位无符号，超过 4GB 的嵌入偏移或单个解压流超过 4GB 时会被截断，导致 FDI 读到错误位置、解压失败或产出损坏文件。同时返回值为有符号 LONG，无法表达 >2GB 的绝对位置（返回 -1 语义又会与真实偏移冲突）。建议偏移参数改为 64 位，并在实现中对不可表示的位置显式失败而非静默取模。

**现有代码**

```c
typedef LONG (*CAB_CALLBACK_SEEK_FILE)(INT_PTR pFile, DWORD dwMove, DWORD dwMoveMethod);
```

**改进建议**

```c
// 注意：偏移必须与原文件 64 位偏移语义一致，禁止截断为 32 位
typedef LONG (*CAB_CALLBACK_SEEK_FILE)(INT_PTR pFile, DWORD64 dw64Move, DWORD dwMoveMethod);
```

#### 61. `tools/wix314/sdk/inc/cabutil.h:18` · 中 / 缺陷

> WRITE_FILE 回调的输出参数名沿用了 READ_FILE 的 pcbRead，语义错误（应为实际写入字节数），实现者容易漏写或按“读取字节数”误用，从而丢失 FDI 的短写校验，造成落盘文件被截断而不报错。此外写入缓冲区应为只读（LPCVOID），避免实现侧意外修改源数据。建议重命名为 pcbWritten 并补注“必须返回实际写入字节数，短写需失败”。

**现有代码**

```c
typedef HRESULT (*CAB_CALLBACK_WRITE_FILE)(INT_PTR pFile, LPVOID pvData, DWORD cbData, DWORD* pcbRead);
```

**改进建议**

```c
typedef HRESULT (*CAB_CALLBACK_WRITE_FILE)(INT_PTR pFile, LPCVOID pvData, DWORD cbData, DWORD* pcbWritten);
```

#### 62. `tools/wix314/sdk/inc/cabutil.h:16` · 中 / 可维护性

> OPEN/BEGIN 回调通过 ppFile 输出句柄，但头文件完全没有声明句柄的所有权与失败清理契约：回调返回失败时 ppFile 是否会写入？成功打开后若后续 READ/WRITE 失败或解压被取消由谁 Close？重复关闭是否允许？契约缺失极易在 CabExtract/CabEnumerate 的失败路径上泄漏文件句柄。建议在 typedef 上补注释明确“失败时不得输出句柄、成功打开的句柄由 Cab* 层负责关闭”。另外 OPEN/READ/WRITE/SEEK/CLOSE 这几个 typedef 在本头文件暴露的 API 中并未被使用（CabExtract/CabEnumerate 都不接收 I/O 回调），若仅供实现内部使用应移入私有头，否则会让调用方误以为可自定义 I/O。

**现有代码**

```c
typedef HRESULT (*CAB_CALLBACK_OPEN_FILE)(LPCWSTR wzFile, INT_PTR* ppFile);
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 63. `tools/wix314/sdk/inc/cabutil.h:38-41` · 高 / 安全

> CabExtract 会把 CAB 内的条目名与 wzExtractDir 拼接后落盘，但接口契约未要求实现做路径规范化与校验。恶意构造的 CAB 条目（绝对路径、盘符、..\..\、ADS/保留名）可逃逸解压目录覆盖任意文件。建议在头注释中明确：实现必须将条目名视为不可信输入，规范化后校验最终路径确实位于 wzExtractDir 之下并拒绝越界条目；同时说明 wzExtractFile 为空/通配时的语义（全量解压）。

**现有代码**

```c
HRESULT DAPI CabExtract(
    __in_z LPCWSTR wzCabinet,
    __in_z LPCWSTR wzExtractFile,
    __in_z LPCWSTR wzExtractDir,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 64. `tools/wix314/sdk/inc/cabutil.h:32-34` · 中 / 可维护性

> 初始化/卸载的生命周期契约缺失且不可失败上报：CabInitialize(fDelayLoad) 未说明是否可重入/幂等、是否内部引用计数、fDelayLoad 与 Import 延迟加载的关系，也未说明多线程并发调用时的同步保证（FDI 会维护全局状态）；CabUninitialize 返回 void，若卸载时仍有活跃的解压操作则无法向调用方报错，也无法被告知“提前卸载导致后续 CabExtract 崩溃”的风险。建议补充成对调用、可重入与线程安全的明确契约，并考虑让 CabUninitialize 返回 HRESULT 或至少说明它在仍有活跃调用时的行为。

**现有代码**

```c
HRESULT DAPI CabInitialize(
    __in BOOL fDelayLoad
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 65. `tools/wix314/sdk/inc/butil.h:5-7` · 中 / 可维护性

> 头文件不具独立可包含性：本文件直接使用 `HRESULT`、`LPCWSTR`、`DWORD`（windows.h）、`DAPI`（dutil.h）以及 `MAX_GUID_CHARS`（本仓库内检索不到其定义，仅 wiutil.h/butil.h 引用），但未包含任何头文件，也未在本文件内定义 `MAX_GUID_CHARS`。同目录的 balutil.h、wcautil.h 都是显式 `#include "dutil.h"` 的模式，本文件却不一致；单独包含 butil.h 时会编译失败或导致 SAL 注解解析错误。建议显式包含 `<windows.h>` 与 `"dutil.h"`（或定义 `MAX_GUID_CHARS`），避免依赖调用方的包含顺序。

**现有代码**

```c
#ifdef __cplusplus
extern "C" {
#endif
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 66. `tools/wix314/sdk/inc/butil.h:11-12` · 中 / 可维护性

> `BUNDLE_INSTALL_CONTEXT` 的枚举值未显式赋值，其数值由声明顺序隐式决定。该枚举作为 `BundleEnumRelatedBundle` 的 ABI 参数跨 DLL 传递，一旦将来在这两个值之间插入新成员或调整顺序，已有调用方传入的数值含义会被静默改变，且编译器不会报错。建议显式固定数值。

**现有代码**

```c
    BUNDLE_INSTALL_CONTEXT_MACHINE,
    BUNDLE_INSTALL_CONTEXT_USER,
```

**改进建议**

```c
    BUNDLE_INSTALL_CONTEXT_MACHINE = 0,
    BUNDLE_INSTALL_CONTEXT_USER = 1,
```

#### 67. `tools/wix314/sdk/inc/butil.h:18-19` · 高 / 安全

> SAL 契约存在漏洞：`lpValueBuf` 的写入长度 `__out_ecount_opt(*pcchValueBuf)` 依赖 `pcchValueBuf`，而后者被标注为 `__inout_opt`（可为 NULL）。因此“传入非空缓冲区 + pcchValueBuf 为 NULL”这一组合是通过 SAL 校验的，函数内部无法得知缓冲区容量，只能按自身长度写入，存在缓冲区溢出风险；实现若直接解引用 `*pcchValueBuf` 则是空指针崩溃。建议对该组合加前置条件（如 `_When_(lpValueBuf != NULL, __notnull)` / `_Pre_notnull_(pcchValueBuf)`），并要求调用方必须提供容量。另外注释中的 `// Bundle code` 与参数名 `szBundleId` 语义不一致，容易被误用为 ProductCode，建议修正注释并补充说明：长度单位是 WCHAR 个数（非字节）、缓冲区不足时应返回 `HRESULT_FROM_WIN32(ERROR_MORE_DATA)` 并在 `*pcchValueBuf` 回写所需字符数（含结尾 NUL）、调用方不得依赖被截断的内容。

**现有代码**

```c
  __out_ecount_opt(*pcchValueBuf) LPWSTR lpValueBuf,     // returned value, NULL if not desired
  __inout_opt                     LPDWORD pcchValueBuf   // in/out buffer character count
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 68. `tools/wix314/sdk/inc/butil.h:25-26` · 中 / 文档

> 枚举游标与结束语义完全未文档化：`pdwStartIndex` 为 `__inout`，但调用方无从得知必须初始化为 0、成功后按何种规则自增、以及枚举结束时返回什么（通常是 `HRESULT_FROM_WIN32(ERROR_NO_MORE_ITEMS)` 还是 `S_FALSE`）。语义不明会导致调用方死循环或漏掉最后一个元素。同时 `lpBundleIdBuf` 的 `__out_ecount(MAX_GUID_CHARS+1)` 隐含了“Bundle Id 一定是 GUID 格式字符串且以 NUL 结尾”的假设，若实际 Id 可为任意字符串则可能被截断或未终止。建议在声明处补充注释（初始值、递进规则、结束返回值、缓冲区格式/终止保证），并对 `pdwStartIndex` 增加 `__in_range(0, MAXDWORD-1)` 之类的约束。

**现有代码**

```c
  __inout  PDWORD pdwStartIndex,
  __out_ecount(MAX_GUID_CHARS+1)  LPWSTR lpBundleIdBuf
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 69. `tools/wix314/sdk/inc/butil.h:24` · 中 / 缺陷

> `context` 参数没有取值范围约束（`__in_range(0, BUNDLE_INSTALL_CONTEXT_USER)`）也没有说明非法值的行为：调用方传入越界值（如 2 或负值）时，实现的行为未定义，可能落入错误的注册表/目录视图（HKLM vs HKCU、ProgramFiles vs LocalAppData）返回错误结果而不报错。建议加 SAL 范围注解，并注释说明各上下文对应的搜索范围及要求（如 per-user 上下文是否需要模拟）。

**现有代码**

```c
  __in     BUNDLE_INSTALL_CONTEXT context,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 70. `tools/wix314/sdk/inc/balutil.h:5` · 高 / 缺陷

> 头文件不自包含：`BalInitialize` 用了 `IBootstrapperEngine*`（定义在 IBootstrapperEngine.h）、`BalLog` 用了 `BOOTSTRAPPER_LOG_LEVEL`（同样在 IBootstrapperEngine.h）、`BalManifestLoad` 用了 `IXMLDOMDocument`（msxml.h），但这里只包含了 dutil.h。目前只有 BalBaseBootstrapperApplication.h 恰好先包含 IBootstrapperEngine.h 才能编译通过，任何直接 `#include "balutil.h"` 的调用方（包括纯 C 或先包含 balutil.h 的场景）都会报类型未定义。建议补上依赖头文件，保证头文件可独立包含。

**现有代码**

```c
#include "dutil.h"
```

**改进建议**

```c
#include "dutil.h"
#include "IBootstrapperEngine.h"
#include <msxml6.h>
```

#### 71. `tools/wix314/sdk/inc/balutil.h:22` · 中 / 缺陷

> 该头文件用 `extern "C"` 声明为 C 可包含，但宏体里使用了 C++ 专有的全局作用域运算符 `::GetLastError()`。一旦被 C 翻译单元使用这两个宏就会编译失败。另外 `DWORD Dutil_er` 在宏块内声明，若调用方作用域已有同名变量会产生 shadow 告警，且宏体未用 do/while(0) 包裹，在无花括号的 if/else 中使用时会出现悬挂 else。建议去掉 `::` 并统一加 do-while 包裹（x 的多次读写也要求调用方传入简单左值，应在注释中说明）。

**现有代码**

```c
#define BalExitOnNullWithLastError(p, x, f) if (NULL == p) { DWORD Dutil_er = ::GetLastError(); x = HRESULT_FROM_WIN32(Dutil_er); if (!FAILED(x)) { x = E_FAIL; } BalLogError(x, f); ExitTrace(x, f); goto LExit; }
```

**改进建议**

```c
#define BalExitOnNullWithLastError(p, x, f) do { if (NULL == p) { DWORD er = GetLastError(); x = HRESULT_FROM_WIN32(er); if (!FAILED(x)) { x = E_FAIL; } BalLogError(x, f); ExitTrace(x, f); goto LExit; } } while (0, 0)
```

#### 72. `tools/wix314/sdk/inc/balutil.h:29` · 中 / 可维护性

> 在公共头文件里定义 `static const HRESULT` 会为每个包含它的翻译单元生成一份独立副本：在 C 下这类静态常量无法作为 switch/case 的常量表达式使用，且在 C/C++ 编译器中容易触发 unused-const-variable 告警（例如 E_MBAHOST_NET452_ON_WIN7RTM 在未使用的 TU 中）。建议改为 `enum`/`#define`，或仅在 .cpp 中定义并通过头文件 `extern const HRESULT` 导出。同时 `#ifndef FACILITY_WIX` 的保护也有隐患：若外部（如其他 SDK/第三方头）以不同值预先定义了该宏，同一 HRESULT 的含义会静默变化，建议增加值校验或改用本项目专属的前缀宏名。

**现有代码**

```c
static const HRESULT E_WIXSTDBA_CONDITION_FAILED = MAKE_HRESULT(SEVERITY_ERROR, FACILITY_WIX, 1);
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 73. `tools/wix314/sdk/inc/balutil.h:47` · 低 / 可维护性

> `BalUninitialize()` 在 C 中表示参数未指定（非原型声明），与头文件的 C 兼容意图不符，也失去了参数检查。应显式写成 `(void)`。

**现有代码**

```c
DAPI_(void) BalUninitialize();
```

**改进建议**

```c
DAPI_(void) BalUninitialize(void);
```

#### 74. `tools/wix314/sdk/inc/balutil.h:63-66` · 中 / 可维护性

> 输出参数用 `__inout` 表达会误导调用方：SAL 语义要求调用前指针已初始化，而函数实际是分配并回写新指针。若实现未先释放原值，调用方复用非 NULL 指针会造成泄漏；同时失败时是否置 NULL 未约定会留下悬垂指针风险。建议改为 `__deref_out`（或 `__out`），并在注释中明确“成功时返回需 StrFree 的新分配字符串、失败时保证置 NULL”。BalGetStringVariable 存在同样问题。

**现有代码**

```c
DAPI_(HRESULT) BalFormatString(
    __in_z LPCWSTR wzFormat,
    __inout LPWSTR* psczOut
    );
```

**改进建议**

```c
DAPI_(HRESULT) BalFormatString(
    __in_z LPCWSTR wzFormat,
    __deref_out LPWSTR* psczOut
    );
```

#### 75. `tools/wix314/sdk/inc/balutil.h:39-41` · 低 / 文档

> `BalInitialize` 接收 `IBootstrapperEngine*` 却未在契约中说明是否 AddRef、调用方是否可在返回后释放该接口、以及是否必须与 `BalUninitialize` 严格配对。这直接决定引擎接口的生命周期与悬垂指针风险，建议在注释中补充所有权/线程约束（例如“不增加引用计数，调用方需保证 pEngine 在 BalUninitialize 之前有效；BalUninitialize 后不应再调用任何 Bal* 接口”）。

**现有代码**

```c
DAPI_(void) BalInitialize(
    __in IBootstrapperEngine* pEngine
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 76. `tools/wix314/sdk/inc/balutil.h:12` · 低 / 可维护性

> 这些错误处理宏未被 do { ... } while (0) 包裹。若调用方写成无花括号的形式（`if (cond) BalExitOnFailure(hr, "..."); else ...`），宏内层的 `if` 会吞掉外部的 `else`，产生编译通过但语义错误的悬挂 else 问题。建议统一包裹为单语句宏。

**现有代码**

```c
#define BalExitOnFailure(x, f) if (FAILED(x)) { BalLogError(x, f); ExitTrace(x, f); goto LExit; }
```

**改进建议**

```c
#define BalExitOnFailure(x, f) do { if (FAILED(x)) { BalLogError(x, f); ExitTrace(x, f); goto LExit; } } while (0)
```

#### 77. `tools/wix314/sdk/inc/cabcutil.h:21` · 中 / 缺陷

> `CABC_HANDLE_BYTES` 既被用作 SAL 的字节数，又隐含要求调用方按此大小分配上下文缓冲区，但它是 `extern const int` 而非编译期常量：在 C 中不是常量表达式（C++ 中由于没有初始化式同样不能用于数组维度），调用方无法写 `BYTE buf[CABC_HANDLE_BYTES]` 或 `static_assert(sizeof(X) == CABC_HANDLE_BYTES)` 做编译期校验；作为跨模块的 const 数据符号还依赖导出表，容易出现取到不同副本或链接错误。建议改为宏或匿名枚举，并补充“调用方必须按该大小、按 HANDLE 对齐分配”的契约说明。

**现有代码**

```c
extern const int CABC_HANDLE_BYTES;
```

**改进建议**

```c
// 调用方必须按此字节数、以 HANDLE 对齐方式分配上下文缓冲区
#define CABC_HANDLE_BYTES 64
```

#### 78. `tools/wix314/sdk/inc/cabcutil.h:41` · 高 / 安全

> 参数类型与 SAL 注解不一致：`phContext` 声明为 `HANDLE *`（语义上只指向一个 HANDLE，x64 为 8 字节），却用 `__out_bcount(CABC_HANDLE_BYTES)` 声明实现会写入 CABC_HANDLE_BYTES 字节。若实现实际是把内部上下文结构体写进该缓冲区，而调用方按类型直觉写成 `HANDLE h = NULL; CabCBegin(..., &h);`，就会造成栈上越界写（内存破坏）。建议改用不透明结构体指针表达上下文，或在头文件中显式说明必须传入 CABC_HANDLE_BYTES 字节缓冲区，并在实现中用 `sizeof`/`static_assert` 保证缓冲区不小于真实上下文结构体。

**现有代码**

```c
    __out_bcount(CABC_HANDLE_BYTES) HANDLE *phContext
```

**改进建议**

```c
    __out_bcount(CABC_HANDLE_BYTES) HANDLE *phContext // 调用方须提供 >= CABC_HANDLE_BYTES 字节且按 HANDLE 对齐的缓冲区
```

#### 79. `tools/wix314/sdk/inc/cabcutil.h:13` · 中 / 文档

> 回调契约不完整，存在悬空指针/误改风险：1) 三个参数都是可变 `LPWSTR`，未说明实现方是否复用内部缓冲区、调用方是否允许就地修改，若调用方修改会破坏实现内部数据；2) 未说明参数在回调返回后是否失效、由谁释放，容易导致调用方保存指针后使用（use-after-free）或尝试释放；3) 缺少 `__in_z_opt` 之类的 SAL 注解，静态分析无法校验。建议参数改为 `LPCWSTR`（若不允许修改）并补充注释，同时声明该回调仅在 `CabCFinish` 调用线程内同步触发、禁止重入同一上下文。

**现有代码**

```c
typedef void (__stdcall * FileSplitCabNamesCallback)(LPWSTR, LPWSTR, LPWSTR);
```

**改进建议**

```c
// 参数仅在回调执行期间有效，回调返回后即失效；调用方不得保存或释放，也不得修改字符串内容。
// 该回调在 CabCFinish 的调用线程内同步触发，禁止重入同一 hContext。
typedef void (__stdcall * FileSplitCabNamesCallback)(__in_z LPCWSTR, __in_z LPCWSTR, __in_z LPCWSTR);
```

#### 80. `tools/wix314/sdk/inc/cabcutil.h:56-58` · 中 / 缺陷

> `CabCCancel` 会销毁上下文并释放 FCI 句柄/临时文件，但参数被标注为 `__in_bcount`（只读输入），会误导 SAL 分析（可能漏报泄漏或误报内存问题），应改为 `__inout_bcount(CABC_HANDLE_BYTES)` 或 `_Frees_ptr_` 之类的“消费指针”注解。同时取消操作返回 `void`，若内部关闭 FCI、删除临时 cab 失败，调用方无法感知也无法重试，残留文件只能静默遗留；建议返回 HRESULT 或至少在注释中明确其永不失败、残留文件的处理责任。

**现有代码**

```c
void DAPI CabCCancel(
    __in_bcount(CABC_HANDLE_BYTES) HANDLE hContext
    );
```

**改进建议**

```c
void DAPI CabCCancel(
    __inout_bcount(CABC_HANDLE_BYTES) HANDLE hContext
    );
```

#### 81. `tools/wix314/sdk/inc/cabcutil.h:54` · 中 / 文档

> 头文件未定义任何错误路径的清理责任，调用方极易泄漏 FCI 上下文与临时文件：`CabCBegin` 失败时 `*phContext` 是否已置 NULL/是否需要调用 `CabCCancel`、`CabCAddFile`/`CabCFinish` 失败后是否必须先 `CabCCancel` 再释放缓冲区、`CabCFinish` 失败时已生成的 cab 文件是否保留，均无说明。另外未声明线程安全边界（同一 hContext 是否允许并发调用、`fileSplitCabNamesCallback` 内能否重入 `CabCAddFile`）。建议在函数声明处补充这些契约，避免调用方在失败分支上重复释放或忘记释放。

**现有代码**

```c
    __in_opt FileSplitCabNamesCallback fileSplitCabNamesCallback
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 82. `tools/wix314/sdk/inc/certutil.h:5-7` · 中 / 缺陷

> 三个 Release 宏都是裸的多语句 `if (...) { ... }`，未用 `do { ... } while (0)` 包裹：
> 1) 在 `if (x) ReleaseCertStore(h); else ...` 这类无花括号用法中，宏展开会吞掉后面的 `else`（dangling-else），导致控制流被破坏；
> 2) 形参 `p` 在宏体中被求值 2~3 次，若实参带副作用（如 `ReleaseCertContext(arr[i++])`）行为不可预期；
> 3) `CertCloseStore`/`CertFreeCertificateContext` 的失败被静默忽略，排查资源泄漏时无任何线索。
> 建议改为 `do { ... } while (0)` 形式；注意该 SDK 的调用点习惯写成不带分号的 `ReleaseXxx(p)`，改造时需同步检查/更新调用点（或用 `while (0)` 结尾且保留分号兼容）。另外宏体里的 `::` 是 C++ 语法，本头文件同时被 `extern "C"` 导出给 C 使用，若在 .c 文件中使用这些宏会编译失败，建议去掉 `::`。

**现有代码**

```c
#define ReleaseCertStore(p) if (p) { ::CertCloseStore(p, 0); p = NULL; }
#define ReleaseCertContext(p) if (p) { ::CertFreeCertificateContext(p); p = NULL; }
#define ReleaseCertChain(p) if (p) { ::CertFreeCertificateChain(p); p = NULL; }
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 83. `tools/wix314/sdk/inc/certutil.h:16-17` · 高 / 缺陷

> SAL 注解自相矛盾：`pvValue` 的 `__out_bcount(*pcbValue)` 会隐式解引用 `pcbValue`，但 `pcbValue` 又被标成 `__out_opt`（可为 NULL）。这会导致：
> 1) 静态分析告警/注解契约不成立（`_bcount` 的 size 参数不应是 optional-out）；
> 2) 若调用方按注解传入 `pcbValue == NULL`，函数内部要么解引用空指针，要么把未初始化的长度当成缓冲区大小，存在越界写风险；
> 3) `pcbValue` 实际语义是“入参给出缓冲区大小、出参返回实际长度”，应标注为 `__inout`，而不是纯 `__out`。
> 建议把 `pcbValue` 改为必填的 `__inout DWORD*`（与其被解引用的事实一致）；如确实需要支持“传 NULL 查询所需长度”，则需改用 `__out_bcount_part_opt(...)` 之类的条件长度注解并在注释中写明调用协议。

**现有代码**

```c
    __out_bcount(*pcbValue) LPVOID pvValue,
    __out_opt DWORD* pcbValue
```

**改进建议**

```c
    __out_bcount(*pcbValue) LPVOID pvValue,
    __inout DWORD* pcbValue
```

#### 84. `tools/wix314/sdk/inc/certutil.h:30` · 中 / 缺陷

> `pfDidCryptAcquire` 的 SAL 方向错误：它语义上是由函数写入的“是否执行过 CryptAcquire”标志（供 `FreeCryptProvFromCert(fAcquired, ...)` 使用），却标注为 `__in BOOL*`。按 `__in` 契约调用方不会初始化为 TRUE，而实现若据此决定是否调用 `CryptReleaseContext`，可能出现句柄未释放（泄漏）或被误释放的情况；同时 `__in` 指针在静态分析下也被假定为已初始化，会掩盖未初始化读取。建议改为 `__out BOOL* pfDidCryptAcquire`，并在注释中明确 `*ppwszTmpContainer`/`*ppwszProviderName` 的所有权归属（由谁分配、必须与 `FreeCryptProvFromCert` 配对释放），避免调用方泄漏或重复释放。

**现有代码**

```c
      __in BOOL *pfDidCryptAcquire,
```

**改进建议**

```c
      __out BOOL *pfDidCryptAcquire,
```

#### 85. `tools/wix314/sdk/inc/certutil.h:46` · 中 / 文档

> `GetProvSecurityDesc` 通过 `__deref_out SECURITY_DESCRIPTOR**` 返回新分配的安全描述符，但头文件中没有说明所有权与释放方式（是 `LocalFree` 还是调用方自行 `HeapFree`/自定义分配器）。调用方极易误用 `ReleaseXxx` 宏或直接泄漏，属于敏感的安全配置内存。建议在声明上方补充注释，明确“返回的 SECURITY_DESCRIPTOR 由调用方用 LocalFree 释放”，或改为更明确的 API（如调用方提供缓冲区 + 大小，配合 `GetSecurityDescriptorLength`）。同时 `SetProvSecurityDesc` 传入的 `pSecurity` 未标注 `__in_opt`，若不允许 NULL 需在注释中说明，以避免误传 NULL 导致提供程序 ACL 被清空的安全隐患。

**现有代码**

```c
      __deref_out SECURITY_DESCRIPTOR** pSecurity
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 86. `tools/wix314/sdk/inc/certutil.h:54-57` · 中 / 缺陷

> `CertHasPrivateKey` 用 `BOOL` 作为唯一返回值，无法区分“证书确实没有私钥”和“CryptoAPI 调用失败（如 `CryptAcquireContext`/`CryptGetUserKey` 返回错误）”。调用方会把失败当成“无私钥”，在签名/安装流程中做出错误决策，且失败原因（NTE_* 错误码）完全丢失，难以诊断。建议改为 `HRESULT CertHasPrivateKey(__in PCCERT_CONTEXT, __out BOOL* pfHasPrivateKey, __out_opt DWORD* pdwKeySpec)`；若为兼容性必须保留 BOOL 签名，请至少在注释中明确失败时的返回值约定（返回 TRUE 还是 FALSE）并保证实现与之一致。

**现有代码**

```c
BOOL DAPI CertHasPrivateKey(
    __in PCCERT_CONTEXT pCertContext,
    __out_opt DWORD* pdwKeySpec
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 87. `tools/wix314/sdk/inc/certutil.h:39-41` · 低 / 可维护性

> `FreeCryptProvFromCert` 的两个字符串参数是输入（仅用于定位/清理临时容器与提供程序），却声明为非 const 的 `LPWSTR`，调用方传入字符串常量或 `LPCWSTR` 时会产生不必要的强转/编译告警，也容易让人误以为函数会修改这些缓冲区。建议改为 `__in_opt LPCWSTR pwszCapiProvider` / `__in_opt LPCWSTR pwszTmpContainer`（实现侧如果确实要写回，请在注释中说明）。

**现有代码**

```c
    __in_opt LPWSTR pwszCapiProvider,
    __in DWORD dwProviderType,
    __in_opt LPWSTR pwszTmpContainer
```

**改进建议**

```c
    __in_opt LPCWSTR pwszCapiProvider,
    __in DWORD dwProviderType,
    __in_opt LPCWSTR pwszTmpContainer
```

#### 88. `tools/wix314/sdk/inc/BalBaseBootstrapperApplication.h:3-4` · 中 / 缺陷

> 该头文件缺少 include guard（`#pragma once` 或 `#ifndef/#define`）。被多个实现文件包含时会导致 `CBalBaseBootstrapperApplication` 重复定义与虚表冲突（同时也不满足 SDK 头文件的常规规范）。

**现有代码**

```c
#include <windows.h>
#include <msiquery.h>
```

**改进建议**

```c
#pragma once

#include <windows.h>
#include <msiquery.h>
```

#### 89. `tools/wix314/sdk/inc/BalBaseBootstrapperApplication.h:657-659` · 高 / 缺陷

> 构造函数直接解引用 `pCommand` 并调用 `pEngine->AddRef()`，没有任何空指针校验；且先对引擎 AddRef（可能触发引擎内部回调线程）再 `InitializeCriticalSection(&m_csCanceled)`，初始化顺序不一致，一旦前者失败或回调早于临界区初始化，后续 CheckCanceled/PromptCancel 会操作未初始化的 CRITICAL_SECTION。建议先判空、先初始化临界区，再持有引擎引用。

**现有代码**

```c
        m_cReferences = 1;
        m_display = pCommand->display;
        m_restart = pCommand->restart;
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 90. `tools/wix314/sdk/inc/BalBaseBootstrapperApplication.h:666-667` · 高 / 缺陷

> `m_dwProgressPercentage` / `m_dwOverallProgressPercentage` 未在构造函数中初始化。嵌入式显示（`BOOTSTRAPPER_DISPLAY_EMBEDDED`）下，`OnCacheAcquireProgress` 与 `OnExecuteProgress` 会直接把这两个成员传给 `SendEmbeddedProgress`，若在 `OnApplyBegin`/`OnProgress` 之前触发，将把未初始化的垃圾值上报给引擎。

**现有代码**

```c
        m_fApplying = FALSE;
        m_fRollingBack = FALSE;
```

**改进建议**

```c
        m_fApplying = FALSE;
        m_fRollingBack = FALSE;
        m_dwProgressPercentage = 0;
        m_dwOverallProgressPercentage = 0;
```

#### 91. `tools/wix314/sdk/inc/BalBaseBootstrapperApplication.h:635-637` · 高 / 缺陷

> 锁的进入/退出之间没有任何读写，`m_fCanceled` 与 `m_fRollingBack` 实际是在锁外读取，临界区形同虚设，存在数据竞争与可见性问题（`PromptCancel` 在另一个线程（UI/关闭消息线程）写入 `m_fCanceled`，`OnSystemShutdown` 也在另一个线程读取 `m_fApplying`）。同样 `IsCanceled()` / `IsRollingBack()` 无锁读取，而 `OnExecutePackageBegin` 写 `m_fRollingBack` 时也不在临界区内。建议把读取放到临界区内，并让所有读写统一走同一把锁。

**现有代码**

```c
        ::EnterCriticalSection(&m_csCanceled);
        ::LeaveCriticalSection(&m_csCanceled);
        return m_fRollingBack ? FALSE : m_fCanceled;
```

**改进建议**

```c
        BOOL fCanceled = FALSE;

        ::EnterCriticalSection(&m_csCanceled);
        fCanceled = m_fRollingBack ? FALSE : m_fCanceled;
        ::LeaveCriticalSection(&m_csCanceled);

        return fCanceled;
```

#### 92. `tools/wix314/sdk/inc/BalBaseBootstrapperApplication.h:280-282` · 高 / 缺陷

> `m_fApplying` 在取消检查之前就被置为 TRUE；如果本次 `OnApplyBegin` 因已取消而返回 `IDCANCEL`，引擎不会发起 apply，也就不会有对应的 `OnApplyComplete` 来复位，导致 `m_fApplying` 永久为 TRUE，`OnSystemShutdown` 会一直拒绝非 critical 的关机请求。建议先判定取消，仅在真正进入 apply 时置 TRUE（或取消路径显式复位）。

**现有代码**

```c
        m_fApplying = TRUE;

        m_dwProgressPercentage = 0;
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 93. `tools/wix314/sdk/inc/BalBaseBootstrapperApplication.h:571-575` · 高 / 缺陷

> `m_fRollingBack` 只在 `OnExecutePackageBegin` 中根据 `fExecute` 赋值，`OnExecuteComplete` / `OnApplyComplete` 都没有复位。最后一个包的 rollback 结束后该标志会一直保持 TRUE，此后 `CheckCanceled()` 永远返回 FALSE，用户的取消请求将被静默忽略。建议在执行/应用结束时清理该状态。

**现有代码**

```c
    virtual STDMETHODIMP_(void) OnExecuteComplete(
        __in HRESULT /*hrStatus*/
        )
    {
    }
```

**改进建议**

```c
    virtual STDMETHODIMP_(void) OnExecuteComplete(
        __in HRESULT /*hrStatus*/
        )
    {
        m_fRollingBack = FALSE;
    }
```

#### 94. `tools/wix314/sdk/inc/BalBaseBootstrapperApplication.h:567-568` · 高 / 缺陷

> 这里重复调用了两次 `CheckCanceled()`（第二次永远走不到有效分支），属于明显的复制粘贴遗留。更关键的是取消时直接返回 `IDCANCEL` 而跳过 `BalRetryEndPackage`，重试状态不会被收尾（见 balretry.h），下一次 `BalRetryStartPackage` 可能按“重试中”处理，造成错误的延时/重试提示。建议始终调用 `BalRetryEndPackage`，再叠加取消结果。

**现有代码**

```c
        int nResult = CheckCanceled() ? IDCANCEL : CheckCanceled() ? IDCANCEL : BalRetryEndPackage(BALRETRY_TYPE_EXECUTE, wzPackageId, NULL, hrExitCode);
        return IDNOACTION == nResult ? nRecommendation : nResult;
```

**改进建议**

```c
        int nResult = BalRetryEndPackage(BALRETRY_TYPE_EXECUTE, wzPackageId, NULL, hrExitCode);
        if (IDNOACTION != nResult)
        {
            return nResult;
        }

        return CheckCanceled() ? IDCANCEL : nRecommendation;
```

#### 95. `tools/wix314/sdk/inc/BalBaseBootstrapperApplication.h:388-389` · 中 / 缺陷

> 与 `OnExecutePackageComplete` 同样的问题：取消时短路返回 `IDCANCEL`，不会调用 `BalRetryEndPackage(BALRETRY_TYPE_CACHE, ...)` 收尾。而 `OnCacheAcquireBegin` 在检查取消之前就已调用了 `BalRetryStartPackage`，因此取消场景下会出现“已 Start 从未 End”的悬空重试状态，影响后续包的重试计数与超时等待。建议先 End 再叠加取消结果。

**现有代码**

```c
        int nResult = CheckCanceled() ? IDCANCEL : BalRetryEndPackage(BALRETRY_TYPE_CACHE, wzPackageOrContainerId, wzPayloadId, hrStatus);
        return IDNOACTION == nResult ? nRecommendation : nResult;
```

**改进建议**

```c
        int nResult = BalRetryEndPackage(BALRETRY_TYPE_CACHE, wzPackageOrContainerId, wzPayloadId, hrStatus);
        if (IDNOACTION != nResult)
        {
            return nResult;
        }

        return CheckCanceled() ? IDCANCEL : nRecommendation;
```

#### 96. `tools/wix314/sdk/inc/BalBaseBootstrapperApplication.h:687` · 低 / 可维护性

> `m_restart` 是 private 成员，在本类中只被赋值、从未被读取，派生类也无法访问；属于无效状态，容易让后续维护者误以为重启策略已被处理。建议删除，或移动到 protected 并提供访问接口供派生类使用。

**现有代码**

```c
    BOOTSTRAPPER_RESTART m_restart;
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 97. `tools/wix314/sdk/inc/buffutil.h:19` · 中 / 缺陷

> 这些导出的函数声明缺少 `DAPI`（`__stdcall`）调用约定，与该 SDK 其余所有公开头文件（如 memutil.h、aclutil.h 中的 `HRESULT DAPI MemFree(...)`）不一致。若实现端按 DAPI 编译（即 __stdcall）而调用方按本头文件使用默认 cdecl，在 x86 下会导致栈不平衡/调用约定不匹配（链接期报错或运行时崩溃），同时也会让静态分析/导出检查失效。建议为全部 8 个函数补齐 `DAPI`。

**现有代码**

```c
HRESULT BuffReadNumber(
```

**改进建议**

```c
HRESULT DAPI BuffReadNumber(
```

#### 98. `tools/wix314/sdk/inc/buffutil.h:51` · 中 / 缺陷

> 写侧缓冲区的 SAL 注解与真实语义不符：
> 1) `__deref_out` 表示返回后缓冲区内容全部由被调方写出（旧内容视作未初始化），但 BuffWrite* 实际是对已有缓冲区追加/扩容（MemReAlloc 保留旧内容），应表达为 inout；
> 2) `bcount(*piBuffer)` 的大小表达式取的是调用前的 `*piBuffer`（首次调用通常为 0，且 `ppbBuffer` 可能为 NULL），而扩容后真正的有效长度是调用后的 `*piBuffer`，分析器因此无法校验新写入的区间，也不会发现写越界/截断；
> 3) 非 `_opt` 的 `_bcount_` 假定缓冲区非空，与“先传 NULL/0 再增长”的调用方式冲突，会产生误报。
> 建议明确 `*piBuffer` 的单位（字节数）并使用 inout/可选 + post 计数语义，例如 `__deref_inout_bcount_opt(*piBuffer)`（必要时配合 `_post_` 计数），并在注释中说明长度契约。

**现有代码**

```c
HRESULT BuffWriteNumber(
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 99. `tools/wix314/sdk/inc/buffutil.h:47` · 中 / 缺陷

> `__deref_out_bcount(*pcbStream)` 的大小表达式引用了声明为 `__out` 的 `pcbStream`：`_bcount_` 的 size 在调用前状态求值，此时 `*pcbStream` 是未定义值，注解实际无效（分析器可能用垃圾长度），且 `__out` 也意味着调用方无法预先提供容量。另外空流（长度为 0）时 `ppbStream` 通常返回 NULL，非 `_opt` 的 `_bcount_` 会误判为非空。建议改为 post-state 计数并允许为空，例如 `__deref_out_bcount_opt(*pcbStream)`（或 `__deref_out_bcount_post_(*pcbStream)`），并明确实现需在返回前先给 `*pcbStream` 赋值、成功时可返回 NULL/0。

**现有代码**

```c
__deref_out_bcount(*pcbStream) BYTE** ppbStream,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 100. `tools/wix314/sdk/inc/buffutil.h:12-14` · 中 / 可维护性

> 这三个别名宏的语义存在隐患：
> 1) `ReleaseMem/ReleaseNullMem` 展开为不带 `do { } while (0)` 的 `if (p) { ... }`，写成 `if (cond) ReleaseBuffer(p); else ...` 时会让 else 意外绑定到内层 if（悬空 else），控制流被静默改变；
> 2) `BuffFree` 直接别名到 `MemFree`，它是返回 HRESULT 的函数且不复位指针，而 `ReleaseBuffer/ReleaseNullBuffer` 走的是释放宏——同一头文件里出现“会置 NULL / 不会置 NULL”两种释放约定，调用方极易混用后产生悬空指针或二次释放，且释放失败（HRESULT）被完全忽略。
> 建议：为 BuffFree 提供会置 NULL 的封装（或直接移除该别名），并为宏加上 `do { } while (0)` 保护，同时在头文件注明各宏的所有权/置空语义。

**现有代码**

```c
#define ReleaseBuffer ReleaseMem
#define ReleaseNullBuffer ReleaseNullMem
#define BuffFree MemFree
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 101. `tools/wix314/sdk/inc/buffutil.h:61` · 中 / 文档

> 字符串 API 的契约不清晰、且读写两侧可空性不一致：
> 1) 写入端 `scz` 为 `__in_z_opt`（允许 NULL），而读取端 `BuffReadString/Ansi` 用 `__deref_out_z`（保证非 NULL、以 NUL 结尾），意味着 NULL 无法往返；需明确 NULL 是写成空串还是写入 NULL 标记，否则读写端实现容易不对称。
> 2) 宽字符写入的实际字节数为 `(wcslen(scz) + 1) * sizeof(WCHAR)`，NUL 终止符是否计入、`*piBuffer` 计的是字节还是元素数都没有说明，容易在调用方产生长度截断/缓冲区不足。
> 建议在声明处补充注释，写清 NULL 处理、终止符与长度单位，并保证与读取端契约一致。

**现有代码**

```c
HRESULT BuffWriteString(
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 102. `tools/wix314/sdk/inc/conutil.h:9` · 高 / 缺陷

> 该宏未用 `do { ... } while (0)` 包裹，只是裸 `if`。当调用方写成 `if (cond) ConsoleExitOnFailure(...); else ...` 时，宏体（含 `goto LExit`）会把 else 挂到自己内部的 if 上，导致控制流错误；同时宏隐式依赖调用方作用域中的 `x`/`LExit`，参数名与局部变量同名时会出问题。另外 `__VA_ARGS__` 为空（如 `ConsoleExitOnFailure(hr, COLOR, "msg")`）会展开成 `f, )`，在 C89/C99 严格模式下是非法尾随逗号，可移植性差。建议统一改为 `do { ... } while (0)` 并将可变参处理为 `f, ##__VA_ARGS__` 或要求至少一个参数。

**现有代码**

```c
#define ConsoleExitOnFailure(x, c, f, ...) if (FAILED(x)) { ConsoleWriteError(x, c, f, __VA_ARGS__); ExitTrace(x, f, __VA_ARGS__); goto LExit; }
```

**改进建议**

```c
#define ConsoleExitOnFailure(x, c, f, ...) do { if (FAILED(x)) { ConsoleWriteError(x, c, f, ##__VA_ARGS__); ExitTrace(x, f, ##__VA_ARGS__); goto LExit; } } while (0)
```

#### 103. `tools/wix314/sdk/inc/conutil.h:14` · 高 / 缺陷

> 宏体里使用了 `::GetLastError()`（全局作用域限定语法），只在 C++ 中合法。该头文件用 `extern "C"` 包装，显然是给 C 场景复用的，但只要被 .c 文件包含，宏一旦展开就会编译失败。应改为不带 `::` 的 `GetLastError()`。另外 `GetLastError()` 只应在判断前立即取值（当前实现正确），但同一表达式中后续调用 `ConsoleWriteError` 会覆盖 last error，务必保持先保存再使用。

**现有代码**

```c
#define ConsoleExitOnLastError(x, c, f, ...) { x = ::GetLastError(); x = HRESULT_FROM_WIN32(x); if (FAILED(x)) { ConsoleWriteError(x, c, f, __VA_ARGS__); ExitTrace(x, f, __VA_ARGS__); goto LExit; } }
```

**改进建议**

```c
#define ConsoleExitOnLastError(x, c, f, ...) do { x = GetLastError(); x = HRESULT_FROM_WIN32(x); if (FAILED(x)) { ConsoleWriteError(x, c, f, ##__VA_ARGS__); ExitTrace(x, f, ##__VA_ARGS__); goto LExit; } } while (0)
```

#### 104. `tools/wix314/sdk/inc/conutil.h:70-72` · 中 / 文档

> `__deref_out_z` 表示由被调方分配缓冲区并通过 `ppwzBuffer` 返回，但头文件没有声明释放方式（CoTaskMemFree / HeapFree / `delete[]` / 其他）以及失败时是否置 NULL。调用方无法安全释放，容易造成内存泄漏或错误释放崩溃；也未说明输入结束后是否要修剪换行/回车。建议在注释里明确所有权、分配器和失败语义（至少失败时将 `*ppwzBuffer` 置 NULL）。

**现有代码**

```c
HRESULT DAPI ConsoleReadW(
    __deref_out_z LPWSTR* ppwzBuffer
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 105. `tools/wix314/sdk/inc/conutil.h:74-78` · 中 / 缺陷

> SAL 契约自相矛盾：`__deref_out_ecount_part(cchCharBuffer, *pcchNumCharReturn)` 中的 `__deref_out` 语义是“由被调方分配并返回”，但紧接着又传入了调用方容量 `cchCharBuffer`（且未标注 `__in`），无法判断缓冲区到底由谁分配、容量是上限还是实际值。同时 `*pcchNumCharReturn` 在同一行被当作“已初始化元素数”的表达式使用，而它自身标注为 `__out`（入口值未定义），静态分析会产生误报。建议明确为“调用方分配定长缓冲区 + 返回实际写入长度”，即 `__deref_out_ecount_z(cchCharBuffer)`（或 `__out_ecount_z`），并把 `cchCharBuffer` 标为 `__in`。

**现有代码**

```c
HRESULT DAPI ConsoleReadStringA(
    __deref_out_ecount_part(cchCharBuffer,*pcchNumCharReturn) LPSTR* szCharBuffer,
    CONST DWORD cchCharBuffer,
    __out DWORD* pcchNumCharReturn
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 106. `tools/wix314/sdk/inc/conutil.h:85-89` · 中 / 缺陷

> `__deref_out_ecount_opt(*pcchSize)` 会用 `*pcchSize` 作为元素数表达式，即要求入口处已定义；但参数 `pcchSize` 却标注为 `__out`（入口值对被调方不可见），两者语义冲突，静态分析会告警，调用方也无法判断应不应当预先初始化容量。此外 `_opt` 表示缓冲区可为 NULL，与 `__deref_out`（必须返回有效指针）又相矛盾。建议把容量与返回长度拆成入/出两个参数，或将 `pcchSize` 改为 `__inout` 并明确“入口为容量、出口为实际长度”的约定。

**现有代码**

```c
HRESULT DAPI ConsoleReadNonBlockingW(
    __deref_out_ecount_opt(*pcchSize) LPWSTR* ppwzBuffer,
    __out DWORD* pcchSize,
    BOOL fReadLine
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 107. `tools/wix314/sdk/inc/conutil.h:91` · 中 / 安全

> 隐藏输入（口令等）相关接口缺少安全约束说明：1) `ConsoleSetReadHidden`/`ConsoleSetReadNormal` 必须成对使用，但接口没有约定“出错或提前返回时自动恢复”，调用方一旦在隐藏状态下异常退出，终端会保持无回显，且在 Ctrl+C 等场景下无法恢复；2) 隐藏输入读取后的缓冲区清零责任未声明，敏感内容可能残留在堆内存中；3) 也不存在把读隐藏输入与恢复合并的原子接口，调用方容易漏掉恢复。建议新增/补充类似 `ConsoleReadHiddenW` 的封装，或在注释中强制要求 `LExit` 路径无条件调用 `ConsoleSetReadNormal()` 并 `SecureZeroMemory` 敏感缓冲区。

**现有代码**

```c
HRESULT DAPI ConsoleSetReadHidden(void);
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 108. `tools/wix314/sdk/inc/conutil.h:45-46` · 低 / 可维护性

> 声明风格不一致：同一头文件中其他无参接口已使用 `(void)`，此处写成 `()`。在 C 中 `()` 表示“参数未指定”（不检查参数），与 `(void)` 语义不同；建议改成 `ConsoleInitialize(void)` 并保持全文件一致。另外 `ConsoleUninitialize` 返回 `void`，无法反馈恢复控制台模式可能出现的失败，若调用方需要保证控制台状态恢复，建议至少返回 `HRESULT` 或在注释中说明忽略失败的原因。

**现有代码**

```c
HRESULT DAPI ConsoleInitialize();
void DAPI ConsoleUninitialize();
```

**改进建议**

```c
HRESULT DAPI ConsoleInitialize(void);
void DAPI ConsoleUninitialize(void);
```

#### 109. `tools/wix314/sdk/inc/custommsierrors.h:25-26` · 中 / 可维护性

> 注释声明的 SERVER 区间为 26001-26100，但本段实际定义到 msierrDependencyHasDependents = 26452（还包含 26101-26109、26201-26205、26251-26254、26301-26352、26401-26405、26451-26452）。任何按 `code >= 26001 && code <= 26100` 做分类/映射的调用方都会漏掉约四分之三的服务器端错误。建议把注释与边界统一（如改为 26001-26500），或重新规划各子段的编号。

**现有代码**

```c
// SERVER range: 26001-26100
#define SERVER_ERROR_BASE                      26000
```

**改进建议**

```c
// SERVER range: 26001-26500
#define SERVER_ERROR_BASE                      26000
```

#### 110. `tools/wix314/sdk/inc/custommsierrors.h:130` · 高 / 缺陷

> PUBLIC 段注释声明范围为 28001-28100，而该错误码取值为 28101，正好越出公共错误区间上界；按区间做“公共错误”判断的代码（如 `code > PUBLIC_ERROR_BASE && code <= 28100`）会把它漏掉。同时它也紧邻下一个类别，后续扩展时容易撞号。建议改为 28026（28001-28025 已占用）或在注释中明确公共段上界为 28101；若该值已随产品发布，需评估修改错误码的兼容性成本。

**现有代码**

```c
#define msierrMsmqCannotConnect                      28101
```

**改进建议**

```c
#define msierrMsmqCannotConnect                      28026
```

#### 111. `tools/wix314/sdk/inc/custommsierrors.h:96-98` · 中 / 缺陷

> MANAGED_ERROR_BASE 与 msierrDotNetRuntimeRequired 取同一个值 27000，基值和真实错误码重叠：调用方若把基值视作占位符，或以 `code - MANAGED_ERROR_BASE` 计算序号，会得到 0 而产生歧义；若把基值也当作合法错误码判断（如 `code == MANAGED_ERROR_BASE`），则无法区分“基值”和“缺少 .NET 运行时”两种情况。建议把基值改为 26900/26999，或让首个错误码从 27001 开始。

**现有代码**

```c
#define MANAGED_ERROR_BASE                     27000

#define msierrDotNetRuntimeRequired            27000
```

**改进建议**

```c
#define MANAGED_ERROR_BASE                     26900

#define msierrDotNetRuntimeRequired            27000
```

#### 112. `tools/wix314/sdk/inc/custommsierrors.h:5` · 低 / 可维护性

> 该头文件全部靠人工分配数字，既没有编译期断言，也没有测试校验“同一值不被重复定义、每个值落在其注释声明的区间内”。本文件已经出现基值与错误码重复（27000）、错误码越界（28101）以及段落注释与实际范围不符等约束破坏，且新增错误码时极易再次发生。建议增加一个自动化测试或生成脚本（扫描所有 `#define msierr*`，断言取值唯一且落在各区间的 base 与上界之间），并在修改编号时强制运行；同时在文件顶部补充各段实际边界的说明。

**现有代码**

```c
#define GLOBAL_ERROR_BASE                 25501
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 113. `tools/wix314/sdk/inc/dirutil.h:7-9` · 中 / 可维护性

> 该枚举被设计为可组合标志位，但缺少 0 值（NONE）以及非法值的约定；同时 DIR_DELETE_SCHEDULE 的语义（延迟到重启后删除？）在头文件中完全没有说明。DirEnsureDeleteEx 接收裸 DWORD，调用方无法从公开契约判断哪些位组合是合法的、未知位是被忽略还是报错。建议补充 DIR_DELETE_NONE = 0（或明确说明不允许 0）、为每个标志添加语义注释，并在注释中说明 DirEnsureDeleteEx 对未知位的处理方式，避免调用方传入非法组合导致误删/漏删。

**现有代码**

```c
    DIR_DELETE_FILES = 1,
    DIR_DELETE_RECURSE = 2,
    DIR_DELETE_SCHEDULE = 4,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 114. `tools/wix314/sdk/inc/dirutil.h:21-25` · 中 / 文档

> DirCreateTempPath 的缓冲区契约不完整：1) cchPath 是否包含结尾 NUL、调用方必须提供多大缓冲（常见约定可能是 MAX_PATH）未说明；2) 失败时 wzPath 的内容（是否被置空、是否保证以 NUL 结尾）未约定，仅靠 __out_ecount_z 无法表达；3) 目标路径已存在时的行为（覆盖/失败）未说明。建议在头文件用注释显式写清成功/失败时对 wzPath 的保证与最小缓冲长度要求，否则调用方容易越界写入或使用未初始化的字符串。

**现有代码**

```c
HRESULT DAPI DirCreateTempPath(
    __in_z LPCWSTR wzPrefix,
    __out_ecount_z(cchPath) LPWSTR wzPath,
    __in DWORD cchPath
    );
```

**改进建议**

```c
// cchPath 为 wzPath 的字符容量（含结尾 NUL）。成功时 wzPath 保证以 NUL 结尾；
// 失败时不保证 wzPath 内容有效，调用方不应使用。
HRESULT DAPI DirCreateTempPath(
    __in_z LPCWSTR wzPrefix,
    __out_ecount_z(cchPath) LPWSTR wzPath,
    __in DWORD cchPath
    );
```

#### 115. `tools/wix314/sdk/inc/dirutil.h:48-50` · 中 / 可维护性

> DirGetCurrent 通过 __deref_out_z 返回新分配的字符串，但头文件未说明分配器与释放方式（MemFree / HeapFree / CoTaskMemFree）。调用方无法得知正确释放函数，容易泄漏或使用不匹配的释放函数导致堆损坏。建议在注释中明确“调用方负责释放，必须使用 XxxFree”。

**现有代码**

```c
HRESULT DAPI DirGetCurrent(
    __deref_out_z LPWSTR* psczCurrentDirectory
    );
```

**改进建议**

```c
// 成功时 *psczCurrentDirectory 为调用方拥有的新分配字符串，用完须用 MemFree 释放。
HRESULT DAPI DirGetCurrent(
    __deref_out_z LPWSTR* psczCurrentDirectory
    );
```

#### 116. `tools/wix314/sdk/inc/dirutil.h:52-54` · 中 / 缺陷

> DirGetCurrent/DirSetCurrent 操作的是进程级当前目录（GetCurrentDirectory/SetCurrentDirectory），在多线程场景下存在天然竞态：其他线程的 SetCurrentDirectory 会使刚刚取得的相对路径失效，也导致按当前目录解析的路径出错。头文件未对线程安全作任何约束。建议至少添加注释声明“非线程安全，调用方需自行串行化，且不得依赖当前目录解析路径”，或在实现文档中点明该限制。

**现有代码**

```c
HRESULT DAPI DirSetCurrent(
    __in_z LPCWSTR wzDirectory
    );
```

**改进建议**

```c
// 非线程安全：操作进程级当前目录，调用方需自行同步，且不要依赖当前目录做相对路径解析。
HRESULT DAPI DirSetCurrent(
    __in_z LPCWSTR wzDirectory
    );
```

#### 117. `tools/wix314/sdk/inc/dirutil.h:43-46` · 中 / 文档

> DirDeleteEmptyDirectoriesToRoot 的返回值语义未定义：DWORD 是 Win32 错误码（如 ERROR_SUCCESS）、还是被删除的目录数量、还是错误码位掩码？dwFlags 也未说明取值来源。调用方无法正确判断失败与否。建议补充返回值与 dwFlags 的注释约定。

**现有代码**

```c
DWORD DAPI DirDeleteEmptyDirectoriesToRoot(
    __in_z LPCWSTR wzPath,
    __in DWORD dwFlags
    );
```

**改进建议**

```c
// 返回 Win32 错误码（ERROR_SUCCESS 表示成功）。
DWORD DAPI DirDeleteEmptyDirectoriesToRoot(
    __in_z LPCWSTR wzPath,
    __in DWORD dwFlags
    );
```

#### 118. `tools/wix314/sdk/inc/dirutil.h:16-19` · 低 / 文档

> DirExists 返回 BOOL，无法区分“路径不存在”和“存在但无权限访问/IO 失败”；相反，成功时 pdwAttributes 可能为 INVALID_FILE_ATTRIBUTES。若调用方据此决定是否创建或删除目录，会把权限问题误判为不存在。建议注释明确 FALSE 的含义（不存在或无法访问），并说明 pdwAttributes 失败时的取值。

**现有代码**

```c
BOOL DAPI DirExists(
    __in_z LPCWSTR wzPath, 
    __out_opt DWORD *pdwAttributes
    );
```

**改进建议**

```c
// 返回 FALSE 表示路径不存在或无法访问（权限/IO 错误无法区分）；
// 失败时 *pdwAttributes 为 INVALID_FILE_ATTRIBUTES。
BOOL DAPI DirExists(
    __in_z LPCWSTR wzPath, 
    __out_opt DWORD *pdwAttributes
    );
```

#### 119. `tools/wix314/sdk/inc/dirutil.h:32-36` · 中 / 可维护性

> 删除接口存在两套并存的契约：DirEnsureDelete 用两个 BOOL（fDeleteFiles、fRecurse），DirEnsureDeleteEx 用 DIR_DELETE 标志位。两个 BOOL 相邻且语义相近，调用方极易在 fDeleteFiles/fRecurse 之间传错参数，造成递归删除范围超出预期（误删）。建议在头文件中注明两者的等价映射关系（DirEnsureDelete → DirEnsureDeleteEx），并尽量统一为标志位接口；若需保留旧接口，至少在注释里给出“等价于 DirEnsureDeleteEx(wzPath, (fDeleteFiles ? DIR_DELETE_FILES : 0) | (fRecurse ? DIR_DELETE_RECURSE : 0))”的说明。

**现有代码**

```c
HRESULT DAPI DirEnsureDelete(
    __in_z LPCWSTR wzPath,
    __in BOOL fDeleteFiles,
    __in BOOL fRecurse
    );
```

**改进建议**

```c
// 等价于 DirEnsureDeleteEx(wzPath, (fDeleteFiles ? DIR_DELETE_FILES : 0) | (fRecurse ? DIR_DELETE_RECURSE : 0))。
HRESULT DAPI DirEnsureDelete(
    __in_z LPCWSTR wzPath,
    __in BOOL fDeleteFiles,
    __in BOOL fRecurse
    );
```

#### 120. `tools/wix314/sdk/inc/deputil.h:9-10` · 中 / 缺陷

> 这两个释放宏存在三个隐患：
> 1) 宏展开为裸 `if`，在 `if (cond) ReleaseDependencyArray(rg, c); else ...` 的调用点会产生悬垂 else（else 被绑定到宏内部的 if），行为与调用方意图不符；
> 2) 参数被多次求值（`rg` 判断一次、传入一次，`c` 判断/传入），若调用方传入带副作用的表达式会被重复执行；
> 3) `ReleaseNullDependencyArray` 只把指针置 NULL 却没有把计数清零，之后若再次调用释放宏，或把旧计数传给 `DepDependencyArrayAlloc`/`DepDependencyArrayFree`，会按失效计数遍历已释放内存，导致二次释放/越界访问。
> 建议对齐本目录 `strutil.h` 中 `ReleaseStrArray`/`ReleaseNullStrArray` 的写法（外层加花括号，并在释放后把计数复位）。

**现有代码**

```c
#define ReleaseDependencyArray(rg, c) if (rg) { DepDependencyArrayFree(rg, c); }
#define ReleaseNullDependencyArray(rg, c) if (rg) { DepDependencyArrayFree(rg, c); rg = NULL; }
```

**改进建议**

```c
#define ReleaseDependencyArray(rg, c) { if (rg) { DepDependencyArrayFree(rg, c); } }
#define ReleaseNullDependencyArray(rg, c) { if (rg) { DepDependencyArrayFree(rg, c); c = 0; rg = NULL; } }
```

#### 121. `tools/wix314/sdk/inc/deputil.h:80-81` · 中 / 可维护性

> 同一模块内“依赖未找到”的错误码契约不一致：`DepGetProviderInformation`/`DepCheckDependency` 声明返回 `E_NOTFOUND`，而本函数以及 `DepUnregisterDependency`/`DepUnregisterDependent` 使用 `E_FILENOTFOUND`。`E_FILENOTFOUND`（FILE 类别 HRESULT）语义上是“文件不存在”，用它表示“注册表里没有这项注册”既不符合 HRESULT 语义，也容易让调用方在只判断 `E_NOTFOUND` 或 `FAILED(hr)` 时把“正常未安装”当成真实故障上报/记日志。建议统一使用 `E_NOTFOUND`（`HRESULT_FROM_WIN32(ERROR_NOT_FOUND)`），若确实需要保留差异，也应在此处明确要求调用方同时处理两种返回码。

**现有代码**

```c
 Note: Returns S_OK if dependent is registered.
       Returns E_FILENOTFOUND if dependent is not registered
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 122. `tools/wix314/sdk/inc/deputil.h:28-30` · 低 / 文档

> 输出字符串的所有权与失败语义未在注释中约定：`psczId`/`psczName` 由被调方分配（预期由调用方 `ReleaseStr` 释放），但头文件没有说明这一点，也没有说明失败路径（如 `E_NOTFOUND`）下是否会把输出参数置为 NULL。调用方若在失败时对未初始化的局部变量执行 `ReleaseStr`，会造成非法释放；若忘记释放则泄漏。建议补充“调用方负责释放，失败时置 NULL”的契约说明。

**现有代码**

```c
    __deref_out_z_opt LPWSTR* psczId,
    __deref_out_z_opt LPWSTR* psczName,
    __out_opt DWORD64* pqwVersion
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 123. `tools/wix314/sdk/inc/deputil.h:129-131` · 低 / 文档

> 容器型输出参数的扩容/失败契约未定义，调用方难以安全清理：`prgDependencies` 是需要 `MemRealloc` 增长的数组，头文件没有说明失败时的不变式——原数组是否仍有效、`*pcDependencies` 是否被改动。若实现先释放旧数组再分配失败，调用方会拿到悬垂指针或直接泄漏整块数组。此外 `pcDependencies` 为 `__inout` 但没有任何上限约束，反复追加存在 UINT 计数溢出的风险。建议在注释中写明“失败时旧数组保持有效且计数不变”，并在实现中对增长做溢出检查。

**现有代码**

```c
DAPI_(HRESULT) DepDependencyArrayAlloc(
    __deref_inout_ecount_opt(*pcDependencies) DEPENDENCY** prgDependencies,
    __inout LPUINT pcDependencies,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 124. `tools/wix314/sdk/inc/dlutil.h:1` · 高 / 缺陷

> 头文件不自包含：本文件直接使用 HRESULT/BOOL/LPVOID/LPWSTR/DWORD64、HINTERNET（wininet.h）、LPPROGRESS_ROUTINE（shlobj.h/shellapi.h）、DAPI 与 SAL 注解，但没有任何 `#include`。同目录的 uriutil.h 就显式包含了 `wininet.h`，aclutil.h/cabcutil.h 也各自包含所需系统头。若调用方先包含 dlutil.h 再包含 windows.h，会因类型未定义而编译失败，或在不同包含顺序下得到不一致的 LPPROGRESS_ROUTINE 声明。建议显式包含依赖头（至少 <windows.h>、<wininet.h>、<shlobj.h>，或本项目统一的 dutil.h）。

**现有代码**

```c
#pragma once
```

**改进建议**

```c
#pragma once
#include <windows.h>
#include <wininet.h>
#include <shlobj.h>
```

#### 125. `tools/wix314/sdk/inc/dlutil.h:29` · 高 / 安全

> sczUser/sczPassword 以明文 LPWSTR 存放凭据，且接口/结构未说明内存所有权（由调用方分配释放？还是 DownloadUrl 内部释放？）与擦除时机。凭据长期驻留在堆上且可能在错误日志/调试输出中被打印，存在泄露风险。建议在注释中明确：所有权归调用方、DownloadUrl 不得保留指针、调用方在使用后必须用 SecureZeroMemory 清零 sczPassword 缓冲区，并要求实现侧日志脱敏；若可改接口，考虑改用 CREDENTIAL/AUTHENTICATION 回调按需提供凭据，避免明文常驻。

**现有代码**

```c
    LPWSTR sczPassword;
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 126. `tools/wix314/sdk/inc/dlutil.h:13` · 中 / 文档

> 认证回调契约未定义：pfRetrySend/pfRetry 是输出参数，但未说明是否允许传 NULL、调用前是否必须由下载器初始化（未初始化即读取会造成未定义行为）、回调返回失败 HRESULT（如 E_ABORT）时下载器是终止下载还是回退为默认认证。建议在 typedef 上方补充注释明确上述语义，或把两个输出参数合并为一个带位标志的枚举。

**现有代码**

```c
    __out BOOL* pfRetrySend,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 127. `tools/wix314/sdk/inc/dlutil.h:17` · 中 / 可维护性

> LPCANCEL_ROUTINE 返回 int 但未定义取值含义（是 PROGRESS_* 语义？还是 0/非 0？），同时 pfnProgress 使用的 LPPROGRESS_ROUTINE 本身也能通过返回值（PROGRESS_CANCEL/PROGRESS_STOP）终止下载，两套取消语义并存且都接收 fAllowRetry 类信息，调用方容易混淆或误取消。另外 pvContext 的线程归属与生命周期、回调是否可重入（是否会在 UI 线程/多个下载线程并发调用）均未说明。建议把返回值改为明确的 BOOL 或具名枚举并补充“回调线程/重入/上下文生命周期”注释。

**现有代码**

```c
typedef int (WINAPI *LPCANCEL_ROUTINE)(
```

**改进建议**

```c
// 返回 TRUE 表示取消下载，FALSE 表示继续；hrError/wzError 为当前错误，fAllowRetry 表示是否允许重试。
// 回调可能在下载线程中被调用，实现需自行保证线程安全且不得在此调用 UI。
typedef BOOL (WINAPI *LPCANCEL_ROUTINE)(
```

#### 128. `tools/wix314/sdk/inc/dlutil.h:48` · 中 / 文档

> DownloadUrl 的参数契约缺失：1) pDownloadSource 标注为 __in 但未说明其内部 sczUser/sczPassword 可为 NULL（匿名/无凭据场景），也未说明函数是否会修改结构；2) wzDestinationPath 标注为 __in 但未说明目录不存在时是否创建、目标文件已存在时是覆盖/跳过/追加 .partial 临时文件、失败时是否会残留部分文件；3) dw64AuthoredDownloadSize 传 0（大小未知/未知 Content-Length）时的语义未定义；4) 未说明 wzDestinationPath 与 pDownloadSource 的生命周期是否必须覆盖整个（可能是异步的）下载过程。建议补齐注释，并把只读入参改为 const DOWNLOAD_SOURCE* 以避免误用。

**现有代码**

```c
HRESULT DAPI DownloadUrl(
```

**改进建议**

```c
// dw64AuthoredDownloadSize 传 0 表示大小未知；目标文件已存在时将被覆盖；
// pDownloadSource / wzDestinationPath 仅在调用期间被引用。
HRESULT DAPI DownloadUrl(
    __in const DOWNLOAD_SOURCE* pDownloadSource,
```

#### 129. `tools/wix314/sdk/inc/dlutil.h:34` · 低 / 可维护性

> DOWNLOAD_CACHE_CALLBACK/DOWNLOAD_AUTHENTICATION_CALLBACK/DOWNLOAD_SOURCE 作为对外 SDK 的公开结构体没有版本号或 cbSize 字段，后续新增成员会破坏已编译调用方的二进制兼容（下载器读越界或调用方传旧尺寸）。建议为这些结构体增加 cbSize（或保留字段）并在 DownloadUrl 中校验，或在注释中明确“结构体布局属于 ABI，禁止直接增删字段”。

**现有代码**

```c
    LPPROGRESS_ROUTINE pfnProgress;
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 130. `tools/wix314/sdk/inc/cryputil.h:5` · 中 / 缺陷

> 该宏展开为裸 if 语句，存在两个实际风险：1) 缺少 do/while(0) 包裹，在 `if (a) ReleaseCryptMsg(m); else ...` 这类无花括号上下文会吞掉/篡改 else 绑定，导致错误的释放路径；2) `p` 被多次求值（判断一次、赋值一次），若传入带副作用的表达式（如 `arr[i++]`）会释放错误的句柄；3) 宏体内使用 `::` 作用域解析符，虽然本头文件用 `extern "C"` 宣称可用于 C，但 C 编译器无法接受 `::`。建议改为 do/while(0) 且使用无限定符的函数名。（注：SDK 中其他 Release* 宏是相同写法，属项目既有风格，但本宏同时隐含上述三个问题，仍建议修正。）

**现有代码**

```c
#define ReleaseCryptMsg(p) if (p) { ::CryptMsgClose(p); p = NULL; }
```

**改进建议**

```c
#define ReleaseCryptMsg(p) do { if (p) { CryptMsgClose(p); p = NULL; } } while (0)
```

#### 131. `tools/wix314/sdk/inc/cryputil.h:56-59` · 中 / 可维护性

> CrypMsgGetParam（以及 CrypDecodeObject 的 ppvObject/pcbObject）会向调用方返回内部新分配的内存，但头文件既未声明分配器，也未提供配套释放函数或释法约定（该族实现依赖 LocalAlloc，调用方必须 LocalFree）。调用方极易按 `delete[]`/`free`/`MemFree` 释放，造成堆损坏；同时 SAL 注解 `__out LPVOID*` 只描述指针本身被写出，并未描述被指向的缓冲区是分配出来的、长度由 pcbData 返回，静态分析无法发现泄漏。建议补充明确的注释约定，并把注解改为 `__deref_out`（有 pcbData 时用 `__deref_out_bcount_opt(*pcbData)`），必要时在头文件中提供 CrypFreeMsgParam/CrypFreeDecodedObject 之类的释放 API。

**现有代码**

```c
    __in DWORD dwType,
    __in DWORD dwIndex,
    __out LPVOID* ppvData,
    __out_opt DWORD* pcbData
```

**改进建议**

```c
    __in DWORD dwType,
    __in DWORD dwIndex,
    __deref_out LPVOID* ppvData,    // 实现方分配，调用方必须用 LocalFree 释放
    __out_opt DWORD* pcbData
```

#### 132. `tools/wix314/sdk/inc/cryputil.h:63-67` · 中 / 安全

> 哈希输出长度与算法之间缺少强制约束：`algid` 由调用方任意指定，`cbHash` 只被当作输出缓冲区长度声明（`__out_bcount(cbHash)`），而没有要求 `cbHash` 必须等于该算法的摘要长度。若调用方传入的缓冲区小于摘要长度且实现未返回 E_INVALIDARG 而是截断写入/仅取前缀，就会得到被截断的哈希用于后续比对，属于安全风险；同时文件中只定义了 `SHA1_HASH_LEN 20`，很容易被误用于 CALG_SHA_256/CALG_MD5 等算法。建议在契约中明确“cbHash 必须等于 algid 的摘要长度，否则返回 E_INVALIDARG”，并按算法分别定义长度常量（如 SHA256_HASH_LEN），实现侧先校验再调用 CryptGetHashParam。

**现有代码**

```c
    __in_z LPCWSTR wzFilePath,
    __in DWORD dwProvType,
    __in ALG_ID algid,
    __out_bcount(cbHash) BYTE* pbHash,
    __in DWORD cbHash,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 133. `tools/wix314/sdk/inc/cryputil.h:89-93` · 中 / 文档

> CrypEncryptMemory/CrypDecryptMemory 同时封装 CryptProtectMemory 与 RtlEncryptMemory（见文件前方的 PFN_* typedef），但 `dwFlags` 未说明属于哪套常量体系：CRYPTPROTECTMEMORY_* 与 RTL_ENCRYPT_OPTION_* 数值语义不同且互不兼容，调用方若按备份的实现传参会在运行时静默失败或得到与预期不同的保护级别（如误用 CRYPTPROTECTMEMORY_SAME_PROCESS 语义）。此外 `cbData` 必须是 `CRYP_ENCRYPT_MEMORY_SIZE`（CRYPTPROTECTMEMORY_BLOCK_SIZE）的整数倍、`pData` 需满足块对齐，头文件对此没有任何约定说明，误用只会得到 crypt E_INVALIDARG。建议在头文件中注明：dwFlags 统一使用 CRYPTPROTECTMEMORY_* 常量、cbData 必须为 CRYP_ENCRYPT_MEMORY_SIZE 的整数倍且不得为 0、pData 对齐要求，并在实现中做参数校验。

**现有代码**

```c
HRESULT DAPI CrypEncryptMemory(
    __inout LPVOID pData,
    __in DWORD cbData,
    __in DWORD dwFlags
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 134. `tools/wix314/sdk/inc/cryputil.h:42-43` · 中 / 可维护性

> CrypInitialize/CrypUninitialize 管理的是全局（进程级）状态，但头文件未说明：是否可重入/引用计数、是否线程安全、以及某个线程调用 CrypUninitialize 时其他线程正在执行 CrypHashFile/CrypEncryptMemory 会怎样（例如缓存的加密提供程序句柄或 RtlEncryptMemory 函数指针被提前释放/置空，后续调用失败或崩溃）。建议在接口契约中声明“必须在使用前初始化、所有使用者退出后才能反初始化”，或改用引用计数实现，至少补充明确的并发约束注释，避免调用方在多线程场景误用。

**现有代码**

```c
HRESULT DAPI CrypInitialize();
void DAPI CrypUninitialize();
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 135. `tools/wix314/sdk/inc/dictutil.h:9-10` · 中 / 缺陷

> 释放宏存在两个隐患：1) 两个宏都没有用 do { ... } while (0) 包裹，在 `if (x) ReleaseDict(p); else ...` 这类无花括号分支中会展开成两个语句，使 else 悬空或编译失败；2) 直接使用 `ReleaseDict` 销毁后指针不会置空，后续误用或再次释放即产生 use-after-free / double free。建议统一用 do-while 包裹，并让非 Null 版本也把句柄置空（或至少只在确实需要保留悬垂指针的场景提供，并在注释中说明风险）。另外 `sdh` 作为宏参数未整体加括号，传入 `a ? b : c` 之类的表达式时语义会被破坏。

**现有代码**

```c
#define ReleaseDict(sdh) if (sdh) { DictDestroy(sdh); }
#define ReleaseNullDict(sdh) if (sdh) { DictDestroy(sdh); sdh = NULL; }
```

**改进建议**

```c
#define ReleaseDict(sdh) do { if (sdh) { DictDestroy(sdh); (sdh) = NULL; } } while (0)
#define ReleaseNullDict(sdh) do { if (sdh) { DictDestroy(sdh); (sdh) = NULL; } } while (0)
```

#### 136. `tools/wix314/sdk/inc/dictutil.h:25-27` · 中 / 文档

> `DictCreateWithEmbeddedKey` 会接收外部数组指针和元素内偏移，`DictAddValue` 接收裸 `void*`，但本头文件没有声明任何所有权/生命周期契约：这个数组是否必须比字典活得久、字典内部是否持有该指针、`DictDestroy` 是否释放数组元素/键字符串/值指针（以及值由谁释放）。缺少这些约定时，调用方极易在数组提前释放后产生悬垂访问，或把值的内存重复释放/泄漏。建议在函数声明旁补充注释，明确“浅引用、不接管所有权、键字符串按需拷贝、DictDestroy 只释放哈希表自身结构”等语义；如果字典确实只是浅引用，建议把参数命名/注释写清楚（例如 `ppvArray` → `ppvArrayToIndex`）。

**现有代码**

```c
    __in DWORD dwNumExpectedItems,
    __in_opt void **ppvArray,
    __in size_t cByteOffset,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 137. `tools/wix314/sdk/inc/dictutil.h:64` · 低 / 可维护性

> 对输入侧句柄使用 `__in_bcount(STRINGDICT_HANDLE_BYTES)` 与句柄的真实语义不符：`STRINGDICT_HANDLE` 是由本模块创建的不透明句柄，不是长度为 `STRINGDICT_HANDLE_BYTES` 的可读字节缓冲区。这样的注解会让静态分析（PREFast/SDV）把任意传入指针当成合法缓冲区，掩盖“传入了非法或已销毁句柄”的问题，也无助于检查句柄的有效性。建议输入句柄统一使用 `__in`（或仅在确实可为 NULL 时用 `__in_opt`），输出句柄使用 `__deref_out`/`__deref_out_opt` 表达“写入句柄指向的指针”，并在注释中说明句柄必须来自 `DictCreate*` 且在使用期间保持有效。

**现有代码**

```c
    __in_bcount(STRINGDICT_HANDLE_BYTES) STRINGDICT_HANDLE sdHandle
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 138. `tools/wix314/sdk/inc/dictutil.h:42` · 低 / 可维护性

> `DictCompareStringListToArray` 是只读查询，却接收非常量的 `STRINGDICT_HANDLE`，与 `DictKeyExists`/`DictGetValue` 使用 `C_STRINGDICT_HANDLE` 的做法不一致。这会让持有 `C_STRINGDICT_HANDLE`（const 句柄）的调用方无法调用比较接口，破坏接口的常量正确性。建议改为 `C_STRINGDICT_HANDLE sdStringList`。

**现有代码**

```c
    __in_bcount(STRINGDICT_HANDLE_BYTES) STRINGDICT_HANDLE sdStringList,
```

**改进建议**

```c
    __in_bcount(STRINGDICT_HANDLE_BYTES) C_STRINGDICT_HANDLE sdStringList,
```

#### 139. `tools/wix314/sdk/inc/dictutil.h:54` · 中 / 文档

> `DictKeyExists` 与 `DictCompareStringListToArray` 用 HRESULT 表达“存在/相等”这类布尔结果，但头文件未定义返回契约：键不存在时是返回 S_FALSE 还是 E_NOTFOUND 之类的失败码？调用方若用 `SUCCEEDED(hr)` 判断，就会把“不存在”和真正的错误（如 E_OUTOFMEMORY）混为一谈；若用 `S_OK == hr` 判断，则错误被当作“不存在”静默吞掉。`DictGetValue` 在键缺失时对 `ppvValue` 的处理同样未说明（是否置 NULL、是否使用 `__deref_out_opt`）。建议在此处补充明确的返回值说明（例如“找到返回 S_OK，未找到返回 S_FALSE，其他为错误”），并为 `ppvValue` 使用 `__deref_out_opt`。

**现有代码**

```c
HRESULT DAPI DictKeyExists(
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 140. `tools/wix314/sdk/inc/gdiputil.h:5` · 中 / 缺陷

> 这三个宏都是用裸 `{ }` 包裹的多语句宏，没有使用 `do { } while (0)`。调用方若写成 `if (cond) ExitOnGdipFailure(g, hr, msg); else ...`，展开后会变成 `if (cond) { ... }; else ...`，多出的分号让 else 悬空，直接编译失败；同时宏内 `x = ...` 的赋值也让 `if (cond) X;` 这类无花括号写法产生难以察觉的控制流错误。建议统一改为 `do { ... } while (0)` 形式（保留内部 goto 语义不变）。

**现有代码**

```c
#define ExitOnGdipFailure(g, x, s) { x = GdipHresultFromStatus(g); if (FAILED(x)) { Dutil_RootFailure(__FILE__, __LINE__, x); ExitTrace(x, s); goto LExit; } }
```

**改进建议**

```c
#define ExitOnGdipFailure(g, x, s) do { x = GdipHresultFromStatus(g); if (FAILED(x)) { Dutil_RootFailure(__FILE__, __LINE__, x); ExitTrace(x, s); goto LExit; } } while (0)
```

#### 141. `tools/wix314/sdk/inc/gdiputil.h:16` · 中 / 文档

> 标注为 `__out` 只声明了指针参数本身被写出，未通过 `__deref_out` 表达“调用方获得一个新分配对象并需自行 delete 的所有权转移语义”，也没有注释说明失败时 `*ppBitmap` 是否被置为 NULL。若实现失败路径未把 `*ppBitmap` 置空，调用方在 `LExit` 清理中 delete 未初始化指针会造成释放野指针。建议改为 `__deref_out Gdiplus::Bitmap **ppBitmap`，并补充注释：成功时由调用方 delete，失败时保证置 NULL。

**现有代码**

```c
    __out Gdiplus::Bitmap **ppBitmap
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 142. `tools/wix314/sdk/inc/gdiputil.h:9-10` · 中 / 缺陷

> 该头文件使用了 `Gdiplus::Bitmap`、`Gdiplus::Status`、`HINSTANCE`、`LPCSTR`、`DAPI`、`__in_opt/__out`（依赖 sal.h）以及 `Dutil_RootFailure`，但文件本身未包含 `<windows.h>`、`<gdiplus.h>`、`sal.h`、`dutil.h`，完全依赖调用方先按正确顺序包含这些头文件，否则不同编译单元会直接编译失败；此外这些宏本身就在文件顶部（不受 `extern "C"` 与 `__cplusplus` 保护）引用了 C++ 的 Gdiplus 与 Dutil 符号。建议在文件开头显式包含所需头文件（或至少在注释中明确记录必须的包含顺序），并把 C++ 专有的 `Gdiplus::` 声明放进 `#ifdef __cplusplus` 保护块，避免被 C 编译单元包含时产生难以定位的报错。

**现有代码**

```c
#ifdef __cplusplus
extern "C" {
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 143. `tools/wix314/sdk/inc/inetutil.h:10` · 中 / 缺陷

> `ReleaseNullInternet` 与 `ReleaseInternet` 实现完全相同，命名却暗示两者行为不同（参考同项目 `wiutil.h` 中 `ReleaseMsi` 只关闭句柄、`ReleaseNullMsi` 关闭后置空）。调用方会误以为 `ReleaseInternet` 不会置空句柄，从而在需要重复判断的场景下产生悬垂句柄/重复 Close 风险。建议：若两者确无差异则删除冗余定义；否则让 `ReleaseInternet` 只关闭不置空，并保持语义与命名一致。

**现有代码**

```c
#define ReleaseNullInternet(h) if (h) { ::InternetCloseHandle(h); h = NULL; }
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 144. `tools/wix314/sdk/inc/inetutil.h:9` · 中 / 缺陷

> 宏未用 `do { ... } while (0)` 包裹且参数未加括号：1) `if (x) ReleaseInternet(h); else ...` 展开后会出现悬挂 else 或编译错误；2) `h` 在宏体中被求值 3 次，传入带副作用的表达式（如 `pArr[i++]`）会被重复求值；3) 参数非左值时 `h = NULL` 直接编译失败。建议整体包装并对参数加括号。

**现有代码**

```c
#define ReleaseInternet(h) if (h) { ::InternetCloseHandle(h); h = NULL; }
```

**改进建议**

```c
#define ReleaseInternet(h) do { if (h) { ::InternetCloseHandle(h); (h) = NULL; } } while (0)
```

#### 145. `tools/wix314/sdk/inc/inetutil.h:5-6` · 低 / 缺陷

> 头文件通过 `extern "C"` 声明为 C 接口，但宏体内使用了 C++ 作用域运算符 `::`，纯 C 编译单元一旦展开该宏就会编译失败，与 `extern "C"` 表达的可移植意图矛盾。建议去掉 `::`（`InternetCloseHandle(h)` / `RegCloseKey(h)` 之类无需全局限定），或至少在注释中明确本头文件仅支持 C++。

**现有代码**

```c
#ifdef __cplusplus
extern "C" {
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 146. `tools/wix314/sdk/inc/inetutil.h:10` · 中 / 可维护性

> 头文件不自包含：声明中用到 `HRESULT`、`DAPI`、`HINTERNET`、`LPFILETIME`、`LPWSTR`、`DWORD`、`LONGLONG` 等类型，但不包含 `<windows.h>`/`<wininet.h>`，也不定义 `DAPI`。调用方必须严格按特定顺序先包含 Windows 头文件与 `dutil.h` 才能编译，顺序错误时错误信息晦涩。建议在此头文件中显式 include 所需依赖（或至少 `#include <windows.h>` + `<wininet.h>`）。

**现有代码**

```c
#define ReleaseNullInternet(h) if (h) { ::InternetCloseHandle(h); h = NULL; }
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 147. `tools/wix314/sdk/inc/inetutil.h:24-28` · 中 / 文档

> `InternetQueryInfoString` 通过 `__deref_out_z LPWSTR*` 返回新分配的字符串，但头文件未说明：1) 内存由谁分配（HeapAlloc/CoTaskMemAlloc/StrAlloc）；2) 调用方应如何释放（本项目通常提供 `ReleaseStr`/`ReleaseNullStr`，此处缺失对应宏，极易按 `free()` 释放造成堆不一致或直接泄漏）；3) 失败时 `*psczValue` 是否保持为 NULL。建议补注释明确所有权与释放方式，并提供配套 `Release` 宏；同时可加 `__outptr` 之类的更精确 SAL。

**现有代码**

```c
HRESULT DAPI InternetQueryInfoString(
    __in HINTERNET h,
    __in DWORD dwInfo,
    __deref_out_z LPWSTR* psczValue
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 148. `tools/wix314/sdk/inc/inetutil.h:30-34` · 中 / 缺陷

> `InternetQueryInfoNumber` 用 `LONG*`（32 位有符号）接收 WinINet 的数值选项。WinINet 多数 INTERNET_OPTION_* 以 `DWORD` 返回，超过 INT_MAX 的值（如累计字节数/超时毫秒数）在 LONG 中会变为负数，造成上层判断（<0 视为错误）误判；部分选项甚至要求 64 位缓冲区。建议改为 `__out DWORD*` 或 `__out LONGLONG*`，或至少在注释中说明仅支持 32 位无符号范围并在函数内做范围校验。

**现有代码**

```c
HRESULT DAPI InternetQueryInfoNumber(
    __in HINTERNET h,
    __in DWORD dwInfo,
    __out LONG* plInfo
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 149. `tools/wix314/sdk/inc/inetutil.h:14-17` · 低 / 文档

> 这几个 API 均返回 HRESULT，但声明处未约定失败路径下输出参数（`*pllSize`/`pft`/`*psczValue`/`*plInfo`）的状态——是保持不变、清零还是未定义。调用方在 `FAILED(hr)` 分支后仍可能读取这些值（尤其 `FILETIME`、`LONGLONG` 未初始化时是 UB）。建议在头文件注释中统一说明：失败时不修改输出参数，并要求调用方先初始化；或在实现中保证失败时清零。

**现有代码**

```c
HRESULT DAPI InternetGetSizeByHandle(
    __in HINTERNET hiFile,
    __out LONGLONG* pllSize
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 150. `tools/wix314/sdk/inc/fileutil.h:9-11` · 中 / 缺陷

> 这三个 Release 宏存在两个隐患：
> 1) 宏体没有用 `do { ... } while (0)` 包裹，直接展开为一条裸 `if`。当调用方写成 `if (cond) ReleaseFile(h); else ...`（无花括号）时，`else` 会挂到宏内部的 `if` 上，产生悬空 else 导致逻辑错误；
> 2) 参数 `h` 在宏体中出现两次（比较与赋值），若传入带副作用的表达式（如函数调用）会被求值两次，可能关闭错误的句柄。
> 另外宏体依赖 `::` 作用域解析，本头文件虽用 `extern "C"` 包裹，但实际无法被纯 C 编译单元使用（FILEMAKEVERSION 中的 `static_cast` 同样如此），建议在头文件中显式声明仅支持 C++。

**现有代码**

```c
#define ReleaseFile(h) if (INVALID_HANDLE_VALUE != h) { ::CloseHandle(h); h = INVALID_HANDLE_VALUE; }
#define ReleaseFileHandle(h) if (INVALID_HANDLE_VALUE != h) { ::CloseHandle(h); h = INVALID_HANDLE_VALUE; }
#define ReleaseFileFindHandle(h) if (INVALID_HANDLE_VALUE != h) { ::FindClose(h); h = INVALID_HANDLE_VALUE; }
```

**改进建议**

```c
#define ReleaseFile(h) do { if (INVALID_HANDLE_VALUE != (h)) { ::CloseHandle(h); (h) = INVALID_HANDLE_VALUE; } } while (0)
#define ReleaseFileHandle(h) do { if (INVALID_HANDLE_VALUE != (h)) { ::CloseHandle(h); (h) = INVALID_HANDLE_VALUE; } } while (0)
#define ReleaseFileFindHandle(h) do { if (INVALID_HANDLE_VALUE != (h)) { ::FindClose(h); (h) = INVALID_HANDLE_VALUE; } } while (0)
```

#### 151. `tools/wix314/sdk/inc/fileutil.h:72-74` · 高 / 缺陷

> `dw64Move` 声明为无符号 `DWORD64`，而底层 `SetFilePointerEx` 的偏移参数是 `LONGLONG`。这导致无法表达负偏移，即使用 `FILE_CURRENT` 回退或 `FILE_END` 向前定位的语义无法实现（负数会被隐式转换为巨大的无符号值，可能一次性把指针移到文件末尾之外且不报错）。建议改为有符号类型。

**现有代码**

```c
HRESULT DAPI FileSetPointer(
    __in HANDLE hFile,
    __in DWORD64 dw64Move,
```

**改进建议**

```c
HRESULT DAPI FileSetPointer(
    __in HANDLE hFile,
    __in LONGLONG llMove,
```

#### 152. `tools/wix314/sdk/inc/fileutil.h:112-114` · 中 / 缺陷

> `cbStartPosition` 和 `cbMaxRead` 都是 32 位 `DWORD`，而同一头文件中的 `FileSetPointer`、`FileSize`、`FileCopyUsingHandles` 均使用 64 位长度。对 >4GB 的文件调用本接口时起始偏移会被截断，无法读取文件后半部分（偏移回绕到低 4GB 区域，可能读到错误数据）。建议起始偏移至少改为 `DWORD64` 以与 `FileSetPointer` 保持一致，并同步更新实现中的偏移计算。

**现有代码**

```c
    __in BOOL fSeek,
    __in DWORD cbStartPosition,
    __in DWORD cbMaxRead,
```

**改进建议**

```c
    __in BOOL fSeek,
    __in DWORD64 cbStartPosition,
    __in DWORD cbMaxRead,
```

#### 153. `tools/wix314/sdk/inc/fileutil.h:140-142` · 中 / 可维护性

> `FileEnsureCopyWithRetry`/`FileEnsureMoveWithRetry` 的路径参数只标注了 `__in`，而对应的非重试版本使用 `__in_z`。缺少 `_z` 契约会让静态分析（/analyze、SAL）不再校验字符串以 NUL 结尾，也可能让调用方误传非终止缓冲区。建议与其它路径参数保持一致。

**现有代码**

```c
HRESULT DAPI FileEnsureCopyWithRetry(
    __in LPCWSTR wzSource,
    __in LPCWSTR wzTarget,
```

**改进建议**

```c
HRESULT DAPI FileEnsureCopyWithRetry(
    __in_z LPCWSTR wzSource,
    __in_z LPCWSTR wzTarget,
```

#### 154. `tools/wix314/sdk/inc/fileutil.h:153-155` · 低 / 可维护性

> `FileEnsureMoveWithRetry` 同样缺少 `__in_z` 注解，与非重试版 `FileEnsureMove` 的契约不一致。

**现有代码**

```c
HRESULT DAPI FileEnsureMoveWithRetry(
    __in LPCWSTR wzSource,
    __in LPCWSTR wzTarget,
```

**改进建议**

```c
HRESULT DAPI FileEnsureMoveWithRetry(
    __in_z LPCWSTR wzSource,
    __in_z LPCWSTR wzTarget,
```

#### 155. `tools/wix314/sdk/inc/fileutil.h:161-166` · 中 / 缺陷

> `ppwzTempFile` 与 `phTempFile` 都是可选出参，因此调用方可以两者都传 NULL：此时文件被创建（磁盘上留下临时文件）但调用方既拿不到路径也拿不到句柄，必然泄漏临时文件。建议把至少一个参数改为必选（如 `__deref_out_z LPWSTR*`），或在实现中显式校验“两者不能同时为 NULL”并返回 E_INVALIDARG；若保留当前签名，需要在注释中写明该前置条件。

**现有代码**

```c
HRESULT DAPI FileCreateTemp(
    __in_z LPCWSTR wzPrefix,
    __in_z LPCWSTR wzExtension,
    __deref_opt_out_z LPWSTR* ppwzTempFile,
    __out_opt HANDLE* phTempFile
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 156. `tools/wix314/sdk/inc/fileutil.h:167-172` · 低 / 可维护性

> `FileCreateTempW` 的签名与 `FileCreateTemp` 完全相同，且本头文件中所有文件接口都已是宽字符版本。带 `W` 后缀的重复声明既没有表达任何差异，也会让调用方困惑该用哪个；若两者是同一实现的两个导出名，建议删除冗余声明或明确注释其区别。

**现有代码**

```c
HRESULT DAPI FileCreateTempW(
    __in_z LPCWSTR wzPrefix,
    __in_z LPCWSTR wzExtension,
    __deref_opt_out_z LPWSTR* ppwzTempFile,
    __out_opt HANDLE* phTempFile
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 157. `tools/wix314/sdk/inc/fileutil.h:53-57` · 中 / 可维护性

> `LPWSTR*` 是二级指针，SAL 注解应使用 `__deref_out_z` 而不是 `__out_z`。当前写法表示“指针本身以 NUL 结尾”，语义错误，静态分析无法校验 `*psczNewFileName` 是有效且以 NUL 结尾的字符串。

**现有代码**

```c
HRESULT DAPI FileAddSuffixToBaseName(
    __in_z LPCWSTR wzFileName,
    __in_z LPCWSTR wzSuffix,
    __out_z LPWSTR* psczNewFileName
    );
```

**改进建议**

```c
HRESULT DAPI FileAddSuffixToBaseName(
    __in_z LPCWSTR wzFileName,
    __in_z LPCWSTR wzSuffix,
    __deref_out_z LPWSTR* psczNewFileName
    );
```

#### 158. `tools/wix314/sdk/inc/fileutil.h:68-71` · 低 / 可维护性

> `psczVersion` 是输出型字符串指针，但只标注了 `__out`，无法表达“返回的字符串以 NUL 结尾且调用方负责释放”的契约；同类问题也存在于 `FileToString` 的 `__out LPWSTR *psczString`。建议统一改为 `__deref_out_z`，与 `FileCreateTemp` 等接口的风格保持一致。

**现有代码**

```c
HRESULT DAPI FileVersionToStringEx(
    __in DWORD64 qwVersion,
    __out LPWSTR* psczVersion
    );
```

**改进建议**

```c
HRESULT DAPI FileVersionToStringEx(
    __in DWORD64 qwVersion,
    __deref_out_z LPWSTR* psczVersion
    );
```

#### 159. `tools/wix314/sdk/inc/iis7util.h:144-147` · 高 / 缺陷

> `vtGet` 是纯输出参数，却标注为 `__in`，会让 SAL/PREfast 静态分析误判容量与生命周期，也会误导调用方以为需要先初始化 VARIANT。建议改为 `__out`，并在注释中说明失败时是否保证已初始化/置空（调用方是否需调用 VariantClear）。

**现有代码**

```c
HRESULT DAPI Iis7GetPropertyVariant(
    __in IAppHostElement *pElement,
    __in LPCWSTR wzPropName,
    __in VARIANT* vtGet
```

**改进建议**

```c
HRESULT DAPI Iis7GetPropertyVariant(
    __in IAppHostElement *pElement,
    __in LPCWSTR wzPropName,
    __out VARIANT* vtGet
```

#### 160. `tools/wix314/sdk/inc/iis7util.h:150-153` · 高 / 缺陷

> `psczGet` 同样是被写出的输出参数，标注 `__in` 属于 SAL 注解错误。另外返回的 LPWSTR 由谁释放（调用方 CoTaskMemFree/delete[]，还是内部缓存）在头文件中没有任何说明，极易造成泄漏或重复释放，建议改为 `__deref_out`/`__out` 并补充所有权约定。

**现有代码**

```c
HRESULT DAPI Iis7GetPropertyString(
    __in IAppHostElement *pElement,
    __in LPCWSTR wzPropName,
    __in LPWSTR* psczGet
```

**改进建议**

```c
HRESULT DAPI Iis7GetPropertyString(
    __in IAppHostElement *pElement,
    __in LPCWSTR wzPropName,
    __out LPWSTR* psczGet
```

#### 161. `tools/wix314/sdk/inc/iis7util.h:109-110` · 中 / 可维护性

> 宏重复定义：`IIS_CONFIG_LIMITS` 在本处与前面的 `L"limits"` 重复；`IIS_CONFIG_ASP_SECTION` 也在 `IIS_CONFIG_STATICCONTENT_SECTION` 后与 `IIS_CONFIG_SESSION` 前各定义了一次；此外 `IIS_CONFIG_SITE_ID` 与 `IIS_CONFIG_ID` 值完全相同（`L"id"`），语义上易混淆。虽然同值重定义在 MSVC 下合法，但后续若只改一处会导致行为不一致，建议删除重复项并统一复用 `IIS_CONFIG_ID`。

**现有代码**

```c
#define IIS_CONFIG_SCRIPTTIMEOUT            L"scriptTimeout"
#define IIS_CONFIG_LIMITS                   L"limits"
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 162. `tools/wix314/sdk/inc/iis7util.h:65-66` · 中 / 可维护性

> 公共宏存在拼写错误：`PEROIDRESTART` 应为 `PERIODRESTART`，同一文件中的 `IDENITITYTYPE` 应为 `IDENTITYTYPE`。这些是 SDK 对外暴露的常量名，一旦被外部代码引用后再重命名会破坏兼容性，建议尽早修正（当前仓库内无其他引用，改名成本低）。

**现有代码**

```c
#define IIS_CONFIG_RECYCLING                L"recycling"
#define IIS_CONFIG_PEROIDRESTART            L"periodicRestart"
```

**改进建议**

```c
#define IIS_CONFIG_RECYCLING                L"recycling"
#define IIS_CONFIG_PERIODRESTART            L"periodicRestart"
```

#### 163. `tools/wix314/sdk/inc/iis7util.h:118` · 中 / 可维护性

> 此头文件直接使用了 `BOOL`/`LPVOID`/`DWORD`/`VARIANT`/`HRESULT` 以及 `IAppHostElement`、`IAppHostElementCollection`、`IAppHostMethod` 等类型，却既未包含 `<windows.h>`/`<ahadmin.h>` 也未做前置声明，头文件无法独立包含，编译是否成功取决于调用方的包含顺序，容易出现难以定位的编译错误。建议显式包含所需系统头（或至少以注释明确声明前置包含要求）。

**现有代码**

```c
typedef BOOL (CALLBACK* ENUMAPHOSTELEMENTPROC)(IAppHostElement*, LPVOID);
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 164. `tools/wix314/sdk/inc/iis7util.h:191-193` · 中 / 文档

> Find/Enum 系列的失败语义未定义：未找到元素时应返回 S_FALSE 还是具体错误码（如 HRESULT_FROM_WIN32(ERROR_NOT_FOUND)）没有约定，也未说明出错时 `ppElement`/`pdwIndex` 是否被置空（*ppElement = NULL、*pdwIndex = 0）。若实现失败路径直接返回而不写输出，调用方若沿用旧值会误用未初始化/残留指针。建议在头文件中明确约定，并把 `IAppHostElement**` 改为 `__deref_out` 或 `__out_opt` 以表达真实契约。

**现有代码**

```c
    __in DWORD dwAttributeValue,
    __out IAppHostElement** ppElement,
    __out DWORD* pdwIndex
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 165. `tools/wix314/sdk/inc/eseutil.h:9-10` · 中 / 缺陷

> 这两个释放宏存在三个隐患：1) 宏体是裸 `if` 语句，未用 `do { } while (0)` 包裹，在 `if (x) ReleaseEseQuery(h); else ...` 场景中 else 会绑定到宏内部 if，导致分支错误；2) `EseFinishQuery` 的 HRESULT 被直接丢弃，查询未真正结束时调用方无从感知，可能造成句柄/游标泄漏；3) `ReleaseEseQuery` 不置空句柄，若调用方在未初始化句柄或重复调用时会读到野指针/重复注销。建议至少在宏内将返回值传出（或断言），并明确要求调用方在 BeginQuery 失败时将句柄置 NULL、优先使用 ReleaseNullEseQuery。

**现有代码**

```c
#define ReleaseEseQuery(pqh) if (pqh) { EseFinishQuery(pqh); }
#define ReleaseNullEseQuery(pqh) if (pqh) { EseFinishQuery(pqh); pqh = NULL; }
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 166. `tools/wix314/sdk/inc/eseutil.h:12-13` · 中 / 缺陷

> 该头文件公开使用了 `JET_INSTANCE/JET_SESID/JET_TABLEID/JET_DBID/JET_COLUMNID/JET_COLTYP` 等 ESE 类型，但文件内没有任何 `#include`。任何单独包含此头的翻译单元都依赖调用方此前恰好包含了 `esent.h`，一旦包含顺序变化就会编译失败（同目录下的 `sceutil.h` 就显式包含了自己的 `sqlce_*.h`）。建议在类型定义前显式包含 `<esent.h>`（放在 `extern "C"` 之内或之外需与该 SDK 头保持一致）。

**现有代码**

```c
struct ESE_COLUMN_SCHEMA
{
```

**改进建议**

```c
#include <esent.h>

struct ESE_COLUMN_SCHEMA
{
```

#### 167. `tools/wix314/sdk/inc/eseutil.h:59-62` · 中 / 缺陷

> `pdsSchema` 标为 `__in`，但 `ESE_TABLE_SCHEMA::jtTable` 与 `ESE_COLUMN_SCHEMA::jcColumn` 显然需要由 `EseEnsureDatabase` 回填给调用方（后续所有 Set/Get 都依赖它们），实际语义是 in/out；而且未说明它是否允许为 NULL、`dwTables/ptsTables` 由谁分配与释放、`fExclusive/fReadonly` 与既有数据库不匹配时的行为（例如只读打开时 schema 缺列如何处理）。SAL 与契约不符会让静态分析失效，也容易导致调用方误以为 schema 可复用/可释放。建议改为 `__inout` 并补充上述契约。

**现有代码**

```c
    __in ESE_DATABASE_SCHEMA *pdsSchema,
    __out JET_DBID* pjdbDb,
    __in BOOL fExclusive,
    __in BOOL fReadonly
```

**改进建议**

```c
    __inout ESE_DATABASE_SCHEMA *pdsSchema,
    __out JET_DBID* pjdbDb,
    __in BOOL fExclusive,
    __in BOOL fReadonly
```

#### 168. `tools/wix314/sdk/inc/eseutil.h:163-164` · 中 / 缺陷

> `__deref_out_bcount(*piBuffer)` 与 `__inout SIZE_T* piBuffer` 组合起来的语义不明确且有实际风险：`*piBuffer` 既是输入容量又是输出字节数，若实现选择“先按容量分配、再填入实际长度”，返回时 `*piBuffer` 若小于缓冲区实际可读字节数尚可，若大于则 bcount 会失效；同时调用方若未初始化 `*piBuffer`，SAL 所描述的长度就是随机值。另外参数名 `piBuffer`（暗示 int 数组）与 `SIZE_T` 字节数不符。建议明确：谁负责分配/释放（是函数分配由调用方 MemFree，还是调用方提供缓冲区），失败时是否保证 `*ppbBuffer = NULL`、`*piBuffer` 是否回写，并统一命名（如 `pcbBuffer`/`pcbResult`）。

**现有代码**

```c
    __deref_out_bcount(*piBuffer) BYTE** ppbBuffer,
    __inout SIZE_T* piBuffer
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 169. `tools/wix314/sdk/inc/eseutil.h:181-182` · 中 / 缺陷

> `ppszValue` 是“指向指针的输出”，`__out` 只表示写入一个指针大小的标量，并未约束其指向的内存；SAL 更准确的写法是 `__deref_out_z LPWSTR*`（若可能返回 NULL 则用 `__deref_out_opt_z`）。更重要的是未说明返回字符串由谁释放（是否为 MemFree/StrFree 配套）、失败时是否写 NULL，调用方很容易直接泄漏或误用 `delete`。建议修正注解并写明所有权契约。

**现有代码**

```c
    __in DWORD dwColumn,
    __out LPWSTR *ppszValue
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 170. `tools/wix314/sdk/inc/eseutil.h:129-131` · 低 / 可维护性

> `ESE_TABLE_SCHEMA tsTable` 以值传递且非 const：结构体内部含 `pcsColumns` 指针，值传递只复制指针而语义上又要求调用方保证数组在调用期间有效，接口契约不清晰；且 `dwColumn` 直接索引 `pcsColumns`，头文件层面看不出是否有越界检查。建议改为 `__in const ESE_TABLE_SCHEMA* tsTable`，同时明确 `dwColumn` 越界时的行为（返回 HRESULT 而不是静默越界）。

**现有代码**

```c
HRESULT DAPI EseSetColumnBinary(
    __in JET_SESID jsSession,
    __in ESE_TABLE_SCHEMA tsTable,
```

**改进建议**

```c
HRESULT DAPI EseSetColumnBinary(
    __in JET_SESID jsSession,
    __in const ESE_TABLE_SCHEMA* ptsTable,
```

#### 171. `tools/wix314/sdk/inc/eseutil.h:109-111` · 中 / 文档

> 事务与更新接口没有任何关于状态机和线程归属的说明：JET 的 `JET_SESID`/`JET_TABLEID` 不是线程安全的，且 `EseBeginTransaction/EseCommitTransaction/EseRollbackTransaction(fAll)` 与 `EsePrepareUpdate/EseFinishUpdate` 必须严格配对、同一 session 上不可并发。如果调用方在多个线程共享同一个 session 或跳过 FinishUpdate 直接回滚，会导致更新未提交/表状态异常。建议在头文件显式声明：这些句柄只允许在创建它们的线程使用、PrepareUpdate 必须与 FinishUpdate 成对调用、回滚后哪些状态仍然有效。

**现有代码**

```c
HRESULT DAPI EseBeginTransaction(
    __in JET_SESID jsSession
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 172. `tools/wix314/sdk/inc/eseutil.h:192-196` · 中 / 缺陷

> `fFinal` 的“其余键列设为 "*"”通配规则存在隐患：1) 对 Binary/Dword/Bool 类型的键列，用字符串 "*" 做通配在类型上并不成立，若实现统一按字符串比较，非文本键可能匹配不到任何行或意外扩大结果集；2) 未说明通配是否只对尾部连续键列有效、重复设置已设过的列与 fFinal 的先后顺序会怎样；3) 调用方无法得知最终构造出的查询条件，误用会悄悄扫全表。建议在接口层限制 fFinal 只能用于文本键列（非文本返回 E_INVALIDARG），或改为显式传入匹配模式，并补全文档。

**现有代码**

```c
HRESULT DAPI EseSetQueryColumnBinary(
    __in ESE_QUERY_HANDLE eqhHandle,
    __in_bcount(cbBuffer) const BYTE* pbBuffer,
    __in SIZE_T cbBuffer,
    __in BOOL fFinal // If this is true, all other key columns in the query will be set to "*"
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 173. `tools/wix314/sdk/inc/jsonutil.h:22-24` · 严重 / 缺陷

> `JSON_VALUE` 被声明为**空结构体**，且没有任何访问器（JsonGetString/JsonGetNumber/JsonGetBool）或初始化/释放函数，导致整套读 API 事实上不可用：调用方拿到 `JSON_VALUE` 后既无法读取内容，也无法释放其中的字符串。另外空结构体是 MSVC/GNU 扩展，在 ISO C 中属于非法写法，若该头被 GCC/Clang 严格模式或其他编译器包含会直接报错。建议补全类型定义（`type` 枚举 + union），或保持不透明但必须同时提供 `JsonValueGetString/GetNumber/GetBool` 与 `JsonUninitializeValue`，并在注释中明确 value 的生命周期（借用 reader 还是独立所有）。

**现有代码**

```c
typedef struct _JSON_VALUE
{
} JSON_VALUE;
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 174. `tools/wix314/sdk/inc/jsonutil.h:5-9` · 高 / 缺陷

> 本头文件使用了 `DAPI_`、`HRESULT`、`LPCWSTR`、`CRITICAL_SECTION`，却没有 `#include "dutil.h"`（同目录的 balutil.h/pathutil.h 等都显式包含），只能依赖调用方的包含顺序，单独包含本头文件会编译失败。CRITICAL_SECTION 还额外依赖 `<windows.h>`，同样未声明。请补上对 dutil.h 的包含（windows.h 由 dutil.h 的既有约定/预编译头保证则可注释说明）。

**现有代码**

```c
#ifdef __cplusplus
extern "C" {
#endif

typedef enum JSON_TOKEN
```

**改进建议**

```c
#include "dutil.h"


#ifdef __cplusplus
extern "C" {
#endif

typedef enum JSON_TOKEN
```

#### 175. `tools/wix314/sdk/inc/jsonutil.h:40-42` · 高 / 缺陷

> `JSON_WRITER` 把最终结果仅存放在 `sczJson` 里，但公共 API 没有 `JsonGetJson`/`JsonDetachJson` 之类的取值函数，也没有说明所有权与调用时序：调用方若直接读 `pWriter->sczJson`，`JsonUninitializeWriter` 之后指针即悬空；若 Uninitialize 不释放，则每次写 JSON 都泄漏。建议补充明确的输出/转移语义，例如 `DAPI_(HRESULT) JsonGetJson(__in JSON_WRITER* pWriter, __out_z LPWSTR* psczJson)`（复制）或 `__out LPWSTR* psczJson`（detach，调用方负责释放），并在头文件注释中写明谁分配、谁释放、在哪个函数之前有效。

**现有代码**

```c
    JSON_TOKEN* rgTokenStack;
    DWORD cTokens;
    DWORD cMaxTokens;
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 176. `tools/wix314/sdk/inc/jsonutil.h:26-29` · 中 / 安全

> 公共结构体直接内嵌 `CRITICAL_SECTION` 存在多处生命周期/并发陷阱：1) 无 `fInitialized` 标志，重复调用 `JsonInitializeReader`（InitializeCriticalSection 二次初始化是 UB）或在初始化失败后的半初始化状态下调用 `JsonUninitializeReader`（DeleteCriticalSection 未初始化锁）都是未定义行为；2) 结构体被按值传递/赋值/`memcpy`（C 调用方很容易这么做）会复制锁状态，导致死锁；3) 若实现内部加锁，而调用方也直接 Lock 暴露出来的 `cs`，同一线程会自死锁；4) 读/写是顺序状态机，多线程交错调用同一实例会破坏 token 状态，但头文件没有标明“同一实例不可并发使用”。建议把锁移入不透明实现（或加 `BOOL fInitialized` 并在注释中明确“不可复制、必须 ZeroMemory 后由 Initialize 初始化一次、同一实例不保证并发安全”）。JSON_WRITER 存在同样问题。

**现有代码**

```c
typedef struct _JSON_READER
{
    CRITICAL_SECTION cs;
    LPWSTR sczJson;
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 177. `tools/wix314/sdk/inc/jsonutil.h:61-64` · 高 / 缺陷

> `JsonReadValue` 的 value 所有权与内存语义完全未定义：参数标成 `__in JSON_VALUE* pValue` 但实际应是 `__out`（由函数填充）；若实现内部为字符串分配内存，调用方没有任何 API 可以释放，必然泄漏；若改复用 reader 内部缓冲，则该值在下一次 `JsonReadNext` 后失效，属于易踩的悬空指针。请在声明与注释中明确：pValue 是否被填充、其中字符串的所有权（借用直到下次读取/UninitializeReader，或需要 JsonUninitializeValue），以及重复调用/在错误 token 下的返回值。

**现有代码**

```c
DAPI_(HRESULT) JsonReadValue(
    __in JSON_READER* pReader,
    __in JSON_VALUE* pValue
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 178. `tools/wix314/sdk/inc/jsonutil.h:79-82` · 中 / 缺陷

> `JsonWriteNumber` 只接受 `DWORD`，无法写出负数、小数/指数形式以及 64 位数值；同时整套写 API 缺少 `JsonWriteNull`（JSON 的 null 是一等值）。调用方只能绕过类型安全直接拼接字符串，一旦遗漏引号/转义就会生成非法 JSON（也是注入类风险的来源）。建议至少提供 `LONGLONG`/`double` 版本并补上 `JsonWriteNull`，或在注释中说明受限原因及调用方应使用的替代路径。

**现有代码**

```c
DAPI_(HRESULT) JsonWriteNumber(
    __in JSON_WRITER* pWriter,
    __in DWORD dwValue
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 179. `tools/wix314/sdk/inc/jsonutil.h:55-59` · 中 / 可维护性

> `JsonReadNext` 缺少状态机契约说明：输入为 NULL/reader 未初始化/JSON 已读完时应返回什么（S_FALSE 还是 E_*）未定义；返回 ARRAY_END、OBJECT_END、OBJECT_KEY 时 `pValue` 是否被写入也未说明，调用方很可能读取未初始化栈变量。此外没有暴露当前解析位置（偏移/行号）的 API，解析失败时无法给出可诊断的错误信息。建议在声明上方注释中明确各 token 下 pValue 的有效性、结束条件、错误码约定，并考虑提供位置查询接口。

**现有代码**

```c
DAPI_(HRESULT) JsonReadNext(
    __in JSON_READER* pReader,
    __out JSON_TOKEN* pToken,
    __out JSON_VALUE* pValue
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 180. `tools/wix314/sdk/inc/jsonutil.h:46-49` · 中 / 缺陷

> `JsonInitializeReader` 的输入所有权未定义，而 `JSON_READER.sczJson` 是非 const 的 `LPWSTR`：若实现只是保存传入的 `LPCWSTR`（不复制，或为了后续 NUL 截断/skip BOM 而强制转换去除 const），就会修改/持有调用方的只读缓冲区，属于未定义行为；若实现是复制，则又没有说明内存开销与释放时机（包含初始化失败时是否已分配）。请在注释中明确“复制一份还是借用调用方缓冲区、生命周期要求”，并使字段类型与实现一致（借用则存 `LPCWSTR`，复制则在失败路径上保证释放）。

**现有代码**

```c
DAPI_(HRESULT) JsonInitializeReader(
    __in_z LPCWSTR wzJson,
    __in JSON_READER* pReader
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 181. `tools/wix314/sdk/inc/locutil.h:1` · 高 / 缺陷

> 头文件不自包含：本文件直接使用了 LPWSTR/BOOL/DWORD/HRESULT/HMODULE/INT_MAX 以及 SAL 注解（__in_z/__out 等）和 DAPI 宏，但没有任何 include。DAPI 定义在同目录的 dutil.h（同目录的 balutil.h、wcautil.h 都显式 `#include "dutil.h"`），INT_MAX 来自 <limits.h>。若调用方先包含本头文件（而非先包含 dutil.h/windows.h），会直接编译失败，且 DAPI 未定义还会改变函数声明含义。建议在文件开头补齐依赖。

**现有代码**

```c
#pragma once
```

**改进建议**

```c
#pragma once

#include <windows.h>
#include "dutil.h"
```

#### 182. `tools/wix314/sdk/inc/locutil.h:16` · 中 / 缺陷

> 在 C 语言中，文件作用域的 `const int X = ...;` 具有外部链接并且不是编译期常量：多个 .c 文件包含本头文件会产生重复符号（链接错误），也无法用于 switch case 或数组维度。C++ 下才有内部链接。建议改为 enum 或宏，保证多 TU 安全且可作为常量表达式。

**现有代码**

```c
const int LOC_CONTROL_NOT_SET = INT_MAX;
```

**改进建议**

```c
enum { LOC_CONTROL_NOT_SET = INT_MAX };
```

#### 183. `tools/wix314/sdk/inc/locutil.h:28` · 中 / 缺陷

> `WIX_LOCALIZATION_LANGUAGE_NOT_SET` 的类型与它要比较的字段 `DWORD dwLangId` 不一致（int 常量 vs DWORD），比较时会触发有符号/无符号转换告警，且 INT_MAX(0x7FFFFFFF) 作为“未设置”语言标记在语义上也不常规（LANGID 通常用 0 或 0xFFFF 表示）。建议与字段同类型定义，并在注释中说明该标记专门只用于 dwLangId。

**现有代码**

```c
const int WIX_LOCALIZATION_LANGUAGE_NOT_SET = INT_MAX;
```

**改进建议**

```c
const DWORD WIX_LOCALIZATION_LANGUAGE_NOT_SET = 0xFFFF; // 仅用于 WIX_LOCALIZATION.dwLangId
```

#### 184. `tools/wix314/sdk/inc/locutil.h:56` · 低 / 可维护性

> 此处（以及 LocGetString、LocAddString）在文件顶部已包裹的 `extern "C" { ... }` 块内又重复写了 `extern "C"`，与同文件其余声明风格不一致，也会让读者误以为这些函数在链接方式上有特殊之处。建议统一删掉函数声明前的 `extern "C"`。

**现有代码**

```c
extern "C" HRESULT DAPI LocProbeForFileEx(
```

**改进建议**

```c
HRESULT DAPI LocProbeForFileEx(
```

#### 185. `tools/wix314/sdk/inc/locutil.h:108` · 中 / 可维护性

> const 正确性不足：入参是 `const WIX_LOCALIZATION*`，却返回可写的 `LOC_CONTROL**`/`LOC_STRING**`，调用方可以绕过 const 直接改写结构体内部数组元素。建议输出改为 `const LOC_CONTROL**`/`const LOC_STRING**`。另外这两个查询接口未找到项时通常返回 S_FALSE 并置空，SAL 用 `__out` 不准确，应为 `__deref_out_opt` 并在注释中写明未找到时的返回值约定。

**现有代码**

```c
    __out LOC_CONTROL** ppLocControl
```

**改进建议**

```c
    __deref_out_opt const LOC_CONTROL** ppLocControl
```

#### 186. `tools/wix314/sdk/inc/locutil.h:99` · 中 / 文档

> 内存所有权语义未定义，风险较高：1) `LocProbeForFile/LocProbeForFileEx` 的 `__inout LPWSTR* psczPath` 与 `LocLocalizeString` 的 `__inout LPWSTR* psczInput` 都没有说明是复用调用方缓冲区、还是函数内部释放旧指针后重新分配（后者要求入参必须是 LocAlloc 分配的指针，否则会破坏堆）；2) `LocGetControl/LocGetString` 返回的是 `rgLocControls`/`rgLocStrings` 内部元素的指针，一旦 `LocAddString` 触发扩容或 `LocFree` 被调用，该指针立即悬垂；3) `LocAddString` 在 realloc 失败时结构体是否保持原状、重复 Id 及 `bOverridable=FALSE` 冲突时的行为均未说明。建议在对应函数注释块中明确这些契约。

**现有代码**

```c
    __inout LPWSTR* psczInput
```

**改进建议**

```c
    __inout LPWSTR* psczInput  // 入参必须是 LocAlloc/CoTaskMem 等可被 LocFree 释放的指针；函数内部释放并重新分配，失败时原指针可能已失效
```

#### 187. `tools/wix314/sdk/inc/locutil.h:121` · 低 / 文档

> `LocAddString` 会修改 `WIX_LOCALIZATION` 的内部动态数组，但注释仅一句“adds a localization string”，未说明成功/失败后结构体状态、重复 Id 覆盖规则以及 `bOverridable` 为 FALSE 时的行为，调用方无法据返回值判断是否需要回滚。建议补充契约说明。

**现有代码**

```c
LocAddString - adds a localization string
```

**改进建议**

```c
LocAddString - adds a localization string

 注意：成功后会重新分配 rgLocStrings，之前 LocGetString 返回的指针失效。
 失败时结构体保持不变。若 Id 已存在：bOverridable=TRUE 时覆盖，否则返回错误。
```

#### 188. `tools/wix314/sdk/inc/iniutil.h:9-10` · 中 / 缺陷

> 这两个释放宏存在 C 宏的典型安全隐患：
> 1) 未用 `do { ... } while (0)` 包裹，在 `if (x) ReleaseIni(h); else ...` 这类写法中会因宏体自带 `if` 而造成悬挂 else；
> 2) 参数 `ih` 未加括号并在条件判断、`IniUninitialize()` 调用和赋值处多次求值，若传入带副作用的表达式（如 `ReleaseNullIni(p->h)` 之类含取指针/自增的写法）会重复执行；
> 3) `ReleaseIni` 释放后不置 NULL，句柄悬空，后续误用或重复释放难以排查（`ReleaseNullIni` 与 `ReleaseIni` 行为不一致也容易误用）。建议统一改为 do-while 并在释放后置 NULL，同时给参数加括号。

**现有代码**

```c
#define ReleaseIni(ih) if (ih) { IniUninitialize(ih); }
#define ReleaseNullIni(ih) if (ih) { IniUninitialize(ih); ih = NULL; }
```

**改进建议**

```c
#define ReleaseIni(ih) do { if (ih) { IniUninitialize(ih); (ih) = NULL; } } while (0)
#define ReleaseNullIni(ih) ReleaseIni(ih)
```

#### 189. `tools/wix314/sdk/inc/iniutil.h:51-52` · 中 / 文档

> `IniGetValueList` 返回的 `INI_VALUE` 数组（以及数组内 `wzName`/`wzValue` 指向的字符串）和 `IniGetValue` 返回的 `LPWSTR` 的归属与生命周期在头文件中没有任何说明，也没有配套的释放函数（如 `IniFreeValueList`/`IniFreeValue`）。调用方无法判断：内存是句柄内部持有（随 `IniUninitialize` 失效）还是由调用方负责释放；一旦按前者理解会导致 use-after-free，按后者理解则会重复释放或泄漏。建议在注释中明确所有权与失效时机（尤其是再次调用 `IniParse`/`IniSetValue` 后旧指针是否失效），必要时新增释放 API。

**现有代码**

```c
    __in_bcount(INI_HANDLE_BYTES) INI_HANDLE piHandle,
    __deref_out_ecount_opt(pcValues) INI_VALUE** prgivValues,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 190. `tools/wix314/sdk/inc/iniutil.h:47` · 低 / 文档

> 字符串参数契约不一致：此处 `wzPath` 以及 `IniGetValue`/`IniSetValue` 的 `wzValueName` 只标了 `__in`，而同文件其他 `LPCWSTR` 参数使用 `__in_z`。`__in` 不含以 NUL 结尾的保证，会让静态分析对缓冲区读取范围判断错误（实现按宽字符串处理，存在越界读风险提示被漏检）。另外 `IniWriteFile` 的 `wzPath` 为 `__in_z_opt`，但未说明传 NULL 时是否回写到 `IniParse` 解析的原始路径，调用方容易误用。建议统一补上 `_z` 并补充 NULL 语义说明。

**现有代码**

```c
    __in LPCWSTR wzPath,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 191. `tools/wix314/sdk/inc/iniutil.h:45-46` · 中 / 可维护性

> 同一不透明句柄会被 `IniParse`/`IniSetValue`/`IniWriteFile` 修改内部状态，但头文件未声明该句柄是否线程安全、是否允许并发调用、是否需要调用方外部加锁。多个线程同时对同一句柄调用解析/写入时会产生数据竞争，调用方无法从 API 契约推断正确用法，建议在此处注明非线程安全（需外部同步）或允许的并发模型。此外读接口 `IniGetValueList`/`IniGetValue` 并不修改句柄，却接收非 const 的 `INI_HANDLE`，已定义的 `C_INI_HANDLE` 完全未被使用，建议读接口改用 `C_INI_HANDLE` 以表达 const 语义。

**现有代码**

```c
HRESULT DAPI IniParse(
    __inout_bcount(INI_HANDLE_BYTES) INI_HANDLE piHandle,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 192. `tools/wix314/sdk/inc/osutil.h:18-19` · 中 / 缺陷

> 枚举顺序存在语义陷阱：`OS_VERSION_WIN7`（真实版本 6.1）排在 `OS_VERSION_WIN2008_R2`（同样基于 6.1，但属于 Server 分支的服务版本）之前，且后续版本只用一个 `OS_VERSION_FUTURE` 兜底。调用方一旦用 `>=`/`<` 之类的枚举数值比较来判断“系统是否足够新”，就会得到错误结论（例如 Win2008 R2 会被判为比 Win7 更新，Win8/Win10/Win11 只能落到 FUTURE）。建议在枚举上明文注明“这些值仅作标识，不可用于大小比较”，或提供 `OsVersionIsAtLeast()` 之类的辅助 API；如果确实需要比较语义，则应把服务版本与客户端版本统一收敛为一个单调常量并在注释中给出映射表。

**现有代码**

```c
    OS_VERSION_WIN7,
    OS_VERSION_WIN2008_R2,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 193. `tools/wix314/sdk/inc/osutil.h:23-26` · 中 / 可维护性

> `OsGetVersion` 用 `void` 返回，导致无法把“查询失败”与“成功但系统未知（OS_VERSION_UNKNOWN）”区分开，也无法表达 `RtlGetVersion`/`GetVersionEx` 失败的场景；同时头文件没有说明输出指针是否可以为 NULL、失败时 `*pVersion`/`*pdwServicePack` 是否被清零。调用方在失败路径上极易读取到未初始化的 DWORD（未定义行为）。建议改为返回 `HRESULT`（保持 ABI 兼容时可另加 `OsGetVersionEx`），并在注释中明确：指针不得为 NULL、成功时保证写入、失败时保证清零。

**现有代码**

```c
void DAPI OsGetVersion(
    __out OS_VERSION* pVersion,
    __out DWORD* pdwServicePack
    );
```

**改进建议**

```c
// pVersion/pdwServicePack 均不可为 NULL；成功时两者被填充，失败时被置为
// OS_VERSION_UNKNOWN / 0（调用方可通过 *pVersion == OS_VERSION_UNKNOWN 判断）。
void DAPI OsGetVersion(
    __out OS_VERSION* pVersion,
    __out DWORD* pdwServicePack
    );
```

#### 194. `tools/wix314/sdk/inc/osutil.h:30-35` · 高 / 安全

> 权限判断接口缺少失败时的安全契约说明：`OsIsRunningPrivileged`/`OsIsUacEnabled` 通过 `HRESULT` 返回，但头文件未声明失败时 `*pfPrivileged`/`*pfUacEnabled` 的取值（未初始化？保持原值？还是 fail-closed 置 FALSE）。由于这些结果常用于决定是否执行提权操作或写入受保护路径，调用方若忽略返回值直接读取输出参数，将把未初始化内存当作权限状态，属于安全敏感缺陷。建议：1) 在注释中明确“失败时输出参数被置为 FALSE（fail-closed），但调用方仍必须先检查 HRESULT”；2) 实现中在入口处先 `*pfXxx = FALSE;`；3) 对指针使用 `__out` 的同时补充 `_In_`/`_Out_` 之外的可空性说明。

**现有代码**

```c
HRESULT DAPI OsIsRunningPrivileged(
    __out BOOL* pfPrivileged
    );
HRESULT DAPI OsIsUacEnabled(
    __out BOOL* pfUacEnabled
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 195. `tools/wix314/sdk/inc/osutil.h:27-29` · 中 / 可维护性

> `OsCouldRunPrivileged` 与 `OsIsRunningPrivileged` 命名差异过小且无注释说明契约，调用方极易选错：前者回答“当前账户是否具备在需要时可提升权限的条件（如管理员组成员 + UAC 允许提升）”，后者回答“当前进程令牌是否已处于提升状态”。两者失败时也都会返回 FALSE，进一步难以区分“无权限”和“查询失败”。建议在声明处补充文档注释，明确各自的判断条件、典型用途（决定是否需要重启提权 vs. 决定是否可直接执行特权操作）以及失败语义。

**现有代码**

```c
HRESULT DAPI OsCouldRunPrivileged(
    __out BOOL* pfPrivileged
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 196. `tools/wix314/sdk/inc/dutil.h:179` · 严重 / 缺陷

> 位布局错误：这里只把 FACILITY_RPC(=1) 与 x 的低位做 OR，既没有把设施码左移到 16~26 位，也没有置严重性位 0x80000000。结果 `HRESULT_FROM_RPC(RPC_S_CALL_FAILED)` 之类的失败码可能落在成功区间，`SUCCEEDED()`/`FAILED()` 判定反转，而 dutil 的 ExitOnFailure 系列完全依赖 FAILED 语义，会导致错误被静默吞掉。应按标准 HRESULT 布局拼装，并只保留被转换码的低 16 位。

**现有代码**

```c
#define HRESULT_FROM_RPC(x) ((HRESULT) ((x) | FACILITY_RPC))
```

**改进建议**

```c
#define HRESULT_FROM_RPC(x) ((HRESULT) (((x) & 0x0000FFFFL) | ((DWORD)FACILITY_RPC << 16) | 0x80000000L))
```

#### 197. `tools/wix314/sdk/inc/dutil.h:201` · 高 / 缺陷

> 符号扩展缺陷：`MAKELONG` 的返回类型是 LONG（有符号），当 build 号 >= 0x8000 时它是负数，直接 `(DWORD64)` 强转会扩展成 0xFFFFFFFF_xxxxxxxx，把高 32 位（major/minor）全部置为 0xFF，版本号被破坏。应先转 `(DWORD)` 再做 64 位扩展；高半部分同理显式转 DWORD 以消除符号性依赖。

**现有代码**

```c
#define MAKEQWORDVERSION(mj, mi, b, r) (((DWORD64)MAKELONG(r, b)) | (((DWORD64)MAKELONG(mi, mj)) << 32))
```

**改进建议**

```c
#define MAKEQWORDVERSION(mj, mi, b, r) (((DWORD64)(DWORD)MAKELONG(r, b)) | (((DWORD64)(DWORD)MAKELONG(mi, mj)) << 32))
```

#### 198. `tools/wix314/sdk/inc/dutil.h:176-177` · 中 / 缺陷

> 该掩码实现隐含两个边界条件却没有任何断言/文档说明：1) 仅当 n 是 2 的幂时结果才正确（n=3 时 roundup(4,3) 得到 4 而非 6）；2) n=0 时 `~((t)0 - 1)` 为 0，静默返回 0；3) x + n - 1 在接近 MAXSIZE_T 时会上溢。另外形参 n 在宏体中被求值两次，若传入 `roundup(p, GetAlign())` 这类有副作用的表达式会被调用两次。建议改名为 `roundup_pow2` 或在宏内对 n 做一次求值并校验非零/2 的幂。

**现有代码**

```c
#define roundup(x, n) roundup_typed(x, n, DWORD)
#define roundup_typed(x, n, t) (((t)(x) + ((t)(n) - 1)) & ~((t)(n) - 1))
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 199. `tools/wix314/sdk/inc/dutil.h:118` · 中 / 缺陷

> 该宏展开为裸 `if` 而非 `do { ... } while (0)`，存在悬垂 else 风险：调用方写 `if (cond) ExitOnFailure(hr, "..."); else Other();` 时，else 会绑定到宏内部的 `if (FAILED(x))`，导致 Other() 在 cond 为真时被意外执行、语义完全改变。建议所有退出宏统一使用 `do { ... } while (0)` 包裹（本文件中的 ExitOnRootFailure/ExitOnNull/ExitOnWin32Error 等同样需要）。

**现有代码**

```c
#define ExitOnFailure(x, s, ...)   if (FAILED(x)) { ExitTrace(x, s, __VA_ARGS__);  goto LExit; }
```

**改进建议**

```c
#define ExitOnFailure(x, s, ...)   do { if (FAILED(x)) { ExitTrace(x, s, __VA_ARGS__); goto LExit; } } while (0)
```

#### 200. `tools/wix314/sdk/inc/dutil.h:105` · 中 / 缺陷

> 块状宏同样缺少 `do { } while (0)` 包裹：调用方按惯例写成 `ExitOnLastError(hr, "...");` 时会展开为 `{ ... };`，多出的分号形成空语句，若外层是 `if/else` 或 `for/while` 无花括号体，会直接编译失败或改变控制流；同时 `Dutil_er` 也暴露了一个可被同名变量遮蔽的局部名。另外此处的 `::` 只适用于 C++，而本头文件用 `extern "C"` 声明了一整组 C API，被 .c 文件包含时会报错。

**现有代码**

```c
#define ExitOnLastError(x, s, ...) { DWORD Dutil_er = ::GetLastError(); x = HRESULT_FROM_WIN32(Dutil_er); if (FAILED(x)) { Dutil_RootFailure(__FILE__, __LINE__, x); ExitTrace(x, s, __VA_ARGS__); goto LExit; } }
```

**改进建议**

```c
#define ExitOnLastError(x, s, ...) do { DWORD Dutil_er = GetLastError(); x = HRESULT_FROM_WIN32(Dutil_er); if (FAILED(x)) { Dutil_RootFailure(__FILE__, __LINE__, x); ExitTrace(x, s, __VA_ARGS__); goto LExit; } } while (0)
```

#### 201. `tools/wix314/sdk/inc/dutil.h:151-152` · 中 / 缺陷

> 两个问题：1) `ReleaseObjectArray` 释放并 `ReleaseMem(prg)` 之后没有把 `prg` 置 NULL（`ReleaseMem` 自身也不置空），若清错/重入路径再次调用会造成重复释放（double free），建议释放后 `prg = NULL; cel = 0;`；2) 该宏使用的 `ReleaseMem` 定义在 memutil.h 中，本头文件并未包含它，单独 include dutil.h 的编译单元一旦使用该宏就会因未定义宏而报错，应显式 `#include "memutil.h"` 或在此处提供依赖说明。此外 `ReleaseObject` 不置空而 `ReleaseNullObject` 置空，两套语义相近的宏容易误用产生悬垂指针，建议在注释中明确区分。

**现有代码**

```c
#define ReleaseObject(x) if (x) { x->Release(); }
#define ReleaseObjectArray(prg, cel) if (prg) { for (DWORD Dutil_ReleaseObjectArrayIndex = 0; Dutil_ReleaseObjectArrayIndex < cel; ++Dutil_ReleaseObjectArrayIndex) { ReleaseObject(prg[Dutil_ReleaseObjectArrayIndex]); } ReleaseMem(prg); }
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 202. `tools/wix314/sdk/inc/dutil.h:66-67` · 低 / 可维护性

> release 分支缺少 `TraceGetLevel()` 的定义（DEBUG 分支有 `#define TraceGetLevel() (REPORT_LEVEL)Dutil_TraceGetLevel()`），导致同一份源码在非 DEBUG 构建下只要调用了 TraceGetLevel() 就会编译失败，Debug/Release 行为不一致。建议在此补上游标：`#define TraceGetLevel() ((REPORT_LEVEL)REPORT_NONE)`（或直接调用 Dutil_TraceGetLevel）。

**现有代码**

```c
#define TraceSetLevel(l, f)
#define Trace(l, f, ...)
```

**改进建议**

```c
#define TraceSetLevel(l, f)
#define TraceGetLevel() ((REPORT_LEVEL)REPORT_NONE)
#define Trace(l, f, ...)
```

#### 203. `tools/wix314/sdk/inc/osutil.h:5-7` · 低 / 可维护性

> 本头文件使用了 `DWORD`、`BOOL`、`HRESULT`、`DAPI`、`__out`，但未 `#include <windows.h>` 或声明这些依赖，完全依赖调用方的 include 顺序（先 windows.h、后 SDK 头）。这与 SDK 惯例一致，但对新接入方是隐蔽的编译失败源。建议至少添加依赖说明注释，或加一层防御：`#if !defined(_WINDOWS_) && !defined(DAPI)` 时给出明确的 `#error` 提示，以便快速定位错误。

**现有代码**

```c
#ifdef __cplusplus
extern "C" {
#endif
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 204. `tools/wix314/sdk/inc/metautil.h:22-25` · 中 / 文档

> `__out_ecount(cchWebBase)` 只表达缓冲区容量，未声明字符串终止语义，也未提供“所需长度”的输出通道。若实现内部用 `StringCchCopy` 之类截断，调用方无法区分“成功但被截断”和“完整成功”，随后按 `%s`/`wcslen` 使用未终止或被截断的路径会得到错误的元数据库路径（甚至越界读）。建议：1) 在注释中明确缓冲区不足时的返回码（如 `HRESULT_FROM_WIN32(ERROR_INSUFFICIENT_BUFFER)`）、是否保证以 NUL 结尾、以及失败时 `wzWebBase` 内容是否有效；2) SAL 改用 `__out_ecount_z(cchWebBase)`；3) 如需让调用方查询所需长度，增加 `__out_opt DWORD* pcchRequired` 之类的可选参数。

**现有代码**

```c
    __in BOOL fSecure,
    __out_ecount(cchWebBase) LPWSTR wzWebBase, 
    __in DWORD cchWebBase
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 205. `tools/wix314/sdk/inc/metautil.h:26-28` · 中 / 文档

> 与 `MetaFindWebBase` 存在同样的契约缺失：调用方通常先用固定长度栈缓冲区（如 `WCHAR wzWebBase[MAX_PATH]`）调用本函数，因此必须明确“缓冲区不足”时的返回码、截断后是否仍以 NUL 结尾、以及是否保证返回的根路径以 `/` 结尾（拼接子键时依赖该假设）。建议补充注释并把 SAL 提升为 `__out_ecount_z(cchWebBase)`。

**现有代码**

```c
HRESULT DAPI MetaFindFreeWebBase(
    __in IMSAdminBaseW* piMetabase, 
    __out_ecount(cchWebBase) LPWSTR wzWebBase, 
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 206. `tools/wix314/sdk/inc/metautil.h:36-38` · 中 / 文档

> `cRetries` 的语义完全没有定义：是总尝试次数还是重试次数（差 1 次）、两次尝试之间是否有 Sleep/指数退避、重试耗尽后返回原始错误还是转换后的错误、以及是否可传 0 表示不重试。调用方无法据此判断最坏耗时（例如 cRetries=10 时是否会阻塞十几秒）与如何可靠处理失败。建议在参数上补充 `__in` 语义说明或加注释明确上述约定，并考虑用 `__deref_out` 之外的方式暴露“最终一次错误码”。

**现有代码**

```c
    __in DWORD dwAccess,
    __in DWORD cRetries,
    __out METADATA_HANDLE* pmh
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 207. `tools/wix314/sdk/inc/metautil.h:46-48` · 低 / 文档

> 内存所有权契约缺失且 SAL 与实现语义可能不一致：`MetaFreeValue` 内部必然要释放 `pmr->pbMDData` 并把指针置空（否则必然产生重复释放），但参数被标注为 `__in` 而非 `__inout`，调用方从签名上看不出记录会被修改。同时 `MetaGetValue` 的 `__inout METADATA_RECORD* pmr` 未说明：`dwMDDataLen`/`pbMDData` 是否必须由调用方预分配、实现是否会在容量不足时自行分配并扩容、以及 Get 成功后即使返回失败是否仍需调用 `MetaFreeValue`。建议补齐注释并统一为 `__inout`。

**现有代码**

```c
void DAPI MetaFreeValue(
    __in METADATA_RECORD* pmr
    );
```

**改进建议**

```c
void DAPI MetaFreeValue(
    __inout METADATA_RECORD* pmr
    );
```

#### 208. `tools/wix314/sdk/inc/metautil.h:5` · 低 / 可维护性

> 本头文件不是自包含的：`DAPI` 宏只在 `dutil.h` 中定义，`HRESULT`/`EXTERN_C` 依赖 `<windows.h>`，但这里既没有包含 `dutil.h` 也没有包含 `<windows.h>`，而只包含了 COM 接口头。任何文件若先包含 `metautil.h` 都会编译失败（`DAPI` 未定义），依赖隐式的包含顺序属于脆弱约定。建议在文件顶部显式包含 `windows.h` 与 `dutil.h`（或至少在注释中写明“必须先包含 dutil.h”）。

**现有代码**

```c
#include <iadmw.h>
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 209. `tools/wix314/sdk/inc/logutil.h:9` · 高 / 缺陷

> 宏存在两个隐患：1) 参数 `x` 被求值三次（`FAILED(x)`、`LogErrorId(x, ...)`、`ExitTrace(x, ...)`），若调用方传入带副作用的表达式（如 `LogExitOnFailure(DoWork(), ...)`）会重复执行，产生重复日志甚至状态不一致；2) 宏体是裸 `if` 语句而非 `do { ... } while (0)`，在 `if (a) LogExitOnFailure(...); else ...` 场景会出现悬垂 else，宏展开后的分号还会截断 if。建议先用局部变量接住 `x`，并用 do/while(0) 包裹（goto LExit 仍可正常跳出）。同理适用于 LogExitOnFailure1/2/3 与 LogExitOnRootFailure*。

**现有代码**

```c
#define LogExitOnFailure(x, i, f) if (FAILED(x)) { LogErrorId(x, i, NULL, NULL, NULL); ExitTrace(x, f); goto LExit; }
```

**改进建议**

```c
#define LogExitOnFailure(x, i, f) do { HRESULT __hrExit_ = (x); if (FAILED(__hrExit_)) { LogErrorId(__hrExit_, i, NULL, NULL, NULL); ExitTrace(__hrExit_, f); goto LExit; } } while (0)
```

#### 210. `tools/wix314/sdk/inc/logutil.h:5-7` · 中 / 可维护性

> 该头文件未包含任何前置依赖头文件，却直接使用 HRESULT/DAPI/HMODULE/HANDLE/DWORD/BOOL/LPCWSTR/LPVOID、SAL 注解（__in/__out_*）、REPORT_LEVEL、HRESULT/FAILED 以及 va_list。这要求调用方严格按特定顺序先包含 windows.h、dutil.h 等，否则编译失败；`va_list` 还需 <stdarg.h>/<cstdarg>（在 `extern "C"` 块内包含 C++ 头需放在块外）。建议提供配套的前置声明头（如 logutil_pre.h）或在本文件顶部显式包含所需依赖，使头文件自包含。

**现有代码**

```c
#ifdef __cplusplus
extern "C" {
#endif
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 211. `tools/wix314/sdk/inc/logutil.h:123-127` · 高 / 缺陷

> 在头文件里用 `inline` 定义具有外部链接的函数存在可移植性风险：C99/C11 语义下 `inline` 定义不产生外部定义，被 C 编译单元调用（尤其取地址时）会得到未解析符号；MSVC 的 C 模式默认也不识别 `inline` 关键字（只有 `__inline`）。LogIdArgs、LogErrorId 同理。建议改为 `static inline`（或项目约定的 `__inline`），避免单一定义/未解析符号问题。

**现有代码**

```c
inline HRESULT LogId(
    __in REPORT_LEVEL rl,
    __in DWORD dwLogId,
    ...
    )
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 212. `tools/wix314/sdk/inc/logutil.h:189-191` · 中 / 缺陷

> `LogStringWorkRaw` 的签名与回调类型 `PFN_LOGSTRINGWORKRAW` 不一致：回调类型带 `DAPI` 调用约定且有两个参数（szString, pvContext），而该导出函数缺少 `DAPI`、也缺少 `pvContext` 参数。若调用方想把它作为 `LogRedirect` 的默认实现传入，会因为函数指针类型不匹配而编译失败（或在 32 位下出现调用约定不一致）。建议统一签名（补 `DAPI` 与 `__in_opt LPVOID pvContext`），或明确注释说明它不能用作回调。

**现有代码**

```c
HRESULT LogStringWorkRaw(
    __in_z LPCSTR szLogData
    );
```

**改进建议**

```c
HRESULT DAPI LogStringWorkRaw(
    __in_z LPCSTR szLogData,
    __in_opt LPVOID pvContext
    );
```

#### 213. `tools/wix314/sdk/inc/logutil.h:194-195` · 中 / 可维护性

> `#define Log LogString` / `#define LogLine LogStringLine` 属于危险的全局标识符替换：会连带污染所有后续包含的头文件与调用方的局部变量、结构体成员、函数名（例如名为 `Log` 的变量或第三方库 API），且报错信息会指向宏而难以定位。建议改为显式函数名，或在宏内部使用带前缀的短别名（如 `LogMsg`）并在文档中说明使用范围。

**现有代码**

```c
#define Log LogString
#define LogLine LogStringLine
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 214. `tools/wix314/sdk/inc/logutil.h:31` · 低 / 可维护性

> `IsLogOpen()` 与 `LogIsOpen()` 语义重复，两种命名风格并存容易让调用方误用其中一个（若内部实现不一致还会出现行为差异）。建议只保留一个（参考 `IsLogInitialized` 的命名），另一个标记为废弃或直接删除。

**现有代码**

```c
BOOL DAPI IsLogOpen();
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 215. `tools/wix314/sdk/inc/logutil.h:86` · 中 / 安全

> `LogGetHandle()` 直接返回内部日志文件句柄，但并未说明所有权与生命周期：调用方若对其调用 CloseHandle 会导致日志模块持有一个失效/可被复用的句柄（后续写入到错误句柄，属于较严重的安全/稳定性风险），而并发调用 LogClose/LogRename 时该句柄也可能立即失效。建议在注释中明确“仅可读不可关闭、仅在日志打开期间有效、不得跨线程持有”，或改为返回值/句柄拷贝并配合引用计数。

**现有代码**

```c
HANDLE DAPI LogGetHandle();
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 216. `tools/wix314/sdk/inc/logutil.h:44` · 低 / 文档

> `LogOpen` 的 `psczLogPath` 未说明内存所有权（由 LogClose 释放还是调用方用 MemoryFree 释放、失败时是否置 NULL）。`__out_z_opt LPWSTR*` 更准确的注解应为 `__deref_opt_out_z LPWSTR*`，否则静态分析无法校验解引用层级；同时建议补充“失败时不分配”的约定，避免调用方泄漏。

**现有代码**

```c
    __out_z_opt LPWSTR* psczLogPath
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 217. `tools/wix314/sdk/inc/logutil.h:49-52` · 中 / 缺陷

> 全局日志状态下这几个 API（LogDisable/LogRedirect/LogClose/LogUninitialize）都没有任何线程安全约定或重入说明。具体风险：若实现持有日志锁期间调用 `vpfLogStringWorkRaw` 回调，而回调内部又调用 `LogString`，会造成自死锁；LogClose 与 LogString 并发时可能出现对已关闭句柄的写入。建议在头文件中显式声明线程模型（例如“所有 Log* 调用需由单一所有者线程串行化”或“内部已加锁，但回调不得重入”），并对重定向回调的重入行为给出明确约束。

**现有代码**

```c
void DAPI LogRedirect(
    __in_opt PFN_LOGSTRINGWORKRAW vpfLogStringWorkRaw,
    __in_opt LPVOID pvContext
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 218. `tools/wix314/sdk/inc/memutil.h:9-10` · 中 / 缺陷

> 这两个释放宏存在典型的宏缺陷：
> 1) 未用 `do { ... } while (0)` 包裹，展开为裸 `if`，调用方写成 `if (cond) ReleaseMem(p); else ...` 时 `else` 会错误地绑定到宏内部的 `if`，产生错误控制流；
> 2) 参数 `p` 未加括号，传入 `a ? b : c`、`pArr[i]`+运算等复合表达式时会因优先级被错误解析；
> 3) `p` 被求值两次，`ReleaseNullMem(pArr[i++])` 这类带副作用的实参会自增两次，可能对错误地址释放或漏置空，造成悬垂指针/重复释放；
> 4) 两者都丢弃了 `MemFree` 的 HRESULT，释放失败时无任何反馈，调用方无法感知。
> 建议改为 `do { } while (0)` 形式并给参数加括号，同时（若需要）对返回值做断言或提供返回 HRESULT 的版本。

**现有代码**

```c
#define ReleaseMem(p) if (p) { MemFree(p); }
#define ReleaseNullMem(p) if (p) { MemFree(p); p = NULL; }
```

**改进建议**

```c
#define ReleaseMem(p) do { if (p) { MemFree(p); } } while (0)
#define ReleaseNullMem(p) do { if (p) { MemFree(p); (p) = NULL; } } while (0)
```

#### 219. `tools/wix314/sdk/inc/memutil.h:19-23` · 中 / 文档

> `MemReAlloc`/`MemReAllocSecure` 的失败语义在接口上没有约定，调用方极易误用：
> - 返回 NULL / 失败 HRESULT 时，原 `pv` 是否仍然有效、是否需要由调用方释放，未作说明（若实现是 realloc 语义，原指针保留，调用方直接 `p = MemReAlloc(p, ...)` 就会泄漏旧内存）；
> - `MemReAllocSecure` 失败时 `*ppvNew` 是否置 NULL（未置空会导致调用方对未初始化指针 Release），以及既有缓冲区在“缩小/移动”时旧副本是否被安全擦除，都没有约定。
> 建议在头文件中用注释明确这些所有权与失败语义，并考虑把入参改为 `__deref_inout`/`__deref_out` 之类的 SAL 以让静态分析捕获误用。

**现有代码**

```c
LPVOID DAPI MemReAlloc(
    __in LPVOID pv,
    __in SIZE_T cbSize,
    __in BOOL fZero
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 220. `tools/wix314/sdk/inc/memutil.h:30-35` · 中 / 缺陷

> 容量计算存在整数溢出风险：`cArray` 为 `DWORD`、`cbArrayType` 为 `SIZE_T`，在 32 位平台上 `cArray * cbArrayType` 以 32 位进行乘法，大数组（如 cArray 接近 4G、cbArrayType>1）会回绕成很小的值，导致分配出远小于需要的缓冲区，后续按索引写入即堆溢出。同时 `dwGrowthCount` 为 0 或极大值时扩容行为也未定义。建议在实现中先做溢出检查（如 `cArray > (SIZE_MAX / cbArrayType)` 直接返回 E_OUTOFMEMORY/HRESULT_FROM_WIN32(ERROR_ARITHMETIC_OVERFLOW)），并在注释中说明 `dwGrowthCount` 的语义与最小值约束。

**现有代码**

```c
HRESULT DAPI MemEnsureArraySize(
    __deref_out_bcount(cArray * cbArrayType) LPVOID* ppvArray,
    __in DWORD cArray,
    __in SIZE_T cbArrayType,
    __in DWORD dwGrowthCount
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 221. `tools/wix314/sdk/inc/memutil.h:37-38` · 中 / 缺陷

> `MemInsertIntoArray` 的 `cExistingArray + cNumInsertItems` 同样是 32 位 DWORD 相加，可发生回绕（DWORD_MAX 附近插入时得到小值），使 SAL 的 `bcount` 注释失真、实际分配不足；并且 `dwInsertIndex` 未做任何约束标注，调用方传入大于 `cExistingArray` 的索引时属于越界写。建议在实现中进行溢出与边界校验（`dwInsertIndex > cExistingArray` 时返回 E_INVALIDARG），并在此处补充 `__in_range`/注释说明索引上限与溢出处理约定。

**现有代码**

```c
    __deref_out_bcount((cExistingArray + cNumInsertItems) * cbArrayType) LPVOID* ppvArray,
    __in DWORD dwInsertIndex,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 222. `tools/wix314/sdk/inc/memutil.h:15-18` · 低 / 可维护性

> 内存 API 的错误模型不一致：`MemAlloc`/`MemReAlloc` 通过返回 NULL 表达失败而无 HRESULT，缺少 `__checkReturn`/`_Ret_maybenull_` 标注，调用方（尤其在此项目大量使用 HRESULT 风格代码的地方）容易漏检 NULL 直接使用；`MemSize` 在 `pv` 无效时会返回什么也未说明。建议为这两个函数加上 `__checkReturn`（或项目约定的 SAL），并在 `MemSize` 上注明对 NULL/非本分配器指针的行为，以统一错误处理风格。

**现有代码**

```c
LPVOID DAPI MemAlloc(
    __in SIZE_T cbSize,
    __in BOOL fZero
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 223. `tools/wix314/sdk/inc/memutil.h:12-13` · 低 / 文档

> 该头文件依赖 `HRESULT`、`DAPI`、`LPVOID`、`__in`/`__deref_out_bcount` 等类型与注解，但不包含任何依赖头（仅 `#pragma once`），能否编译完全取决于调用方的 include 顺序；同时 `MemInitialize` 返回 HRESULT 而 `MemUninitialize` 返回 void，未说明重复初始化/反初始化的幂等性以及未初始化即调用 MemAlloc 的行为，也未说明多线程下初始化与分配的线程安全性约定。建议加入必要的依赖头（或明确注释所需前置头），并补充初始化生命周期与线程安全约定。

**现有代码**

```c
HRESULT DAPI MemInitialize();
void DAPI MemUninitialize();
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 224. `tools/wix314/sdk/inc/perfutil.h:13-14` · 中 / 缺陷

> `PerfInitialize` 返回 `void`，调用方无法得知 QPC 初始化（`QueryPerformanceFrequency`）是否成功；若实现内部把频率保存为 0，后续 `PerfConvertToSeconds` 做除法会产生除零/无穷值，且错误会静默传播到上层计时展示。建议改为返回 `HRESULT`/`BOOL`，并在注释中写明“必须先调用、失败后其它接口行为未定义”，或至少提供 `PerfIsInitialized()` 之类的状态查询；同时说明该接口是否幂等/线程安全（初始化与读取之间的全局状态竞态）。

**现有代码**

```c
void DAPI PerfInitialize(
    );
```

**改进建议**

```c
HRESULT DAPI PerfInitialize(
    );
BOOL DAPI PerfIsInitialized(
    );
```

#### 225. `tools/wix314/sdk/inc/perfutil.h:15-17` · 中 / 文档

> `__out_opt` 允许传入 NULL，但头文件没有任何契约说明：传 NULL 时是“仅记录起点、不输出”、还是完全无操作？另外名字 `PerfClickTime` 无法表达输出到底是“自上次点击以来的耗时”还是“当前绝对 QPC tick”，也没有说明多次调用是累加还是覆盖，调用方极易误用。建议补充契约注释并考虑把参数收窄为 `__out`（若 NULL 无实际意义）。

**现有代码**

```c
void DAPI PerfClickTime(
    __out_opt LARGE_INTEGER* pliElapsed
    );
```

**改进建议**

```c
// 输出自上次 PerfClickTime 调用（或 PerfInitialize）以来的 QPC tick 差值；
// pliElapsed 为 NULL 时不输出但仍推进计时刻点。
void DAPI PerfClickTime(
    __out_opt LARGE_INTEGER* pliElapsed
    );
```

#### 226. `tools/wix314/sdk/inc/perfutil.h:18-20` · 中 / 缺陷

> 该函数未声明任何失败语义：`pli` 为 NULL 或 `PerfInitialize` 未被调用/初始化失败（频率为 0）时会返回 NaN/Inf 甚至触发除零异常，而返回值 `double` 无法与正常耗时区分。建议在头文件中明确前置条件（必须先成功调用 `PerfInitialize`、`pli` 不可为 NULL），或改为 `HRESULT PerfConvertToSeconds(__in const LARGE_INTEGER* pli, __out double* pdSeconds)` 以便校验失败。

**现有代码**

```c
double DAPI PerfConvertToSeconds(
    __in const LARGE_INTEGER* pli
    );
```

**改进建议**

```c
// 前置条件：PerfInitialize 已成功调用；pli 非空。
double DAPI PerfConvertToSeconds(
    __in const LARGE_INTEGER* pli
    );
```

#### 227. `tools/wix314/sdk/inc/polcutil.h:9` · 高 / 缺陷

> 在头文件作用域以 `const LPCWSTR` 定义常量存在两个问题：
> 1) 在 C 编译单元中，文件作用域的 `const` 变量默认是 **外部链接**（与 C++ 不同），本头文件又被 `extern "C"` 包裹，一旦被两个及以上的 .c 文件包含，就会产生重复定义/多重符号链接错误（现代 GCC 默认 `-fno-common` 会直接报 multiple definition）。
> 2) `const LPCWSTR` 修饰的是指针本身（等价 `const WCHAR* const`），并非表达“字符串内容不可变”的意图，容易让人误解；此外该常量目前在整个仓库中无任何引用，属于头文件级别的冗余定义。
> 建议改为宏、`static const`，或“头文件 `extern` 声明 + 单个 .c 中定义”。

**现有代码**

```c
const LPCWSTR POLICY_BURN_REGISTRY_PATH = L"WiX\\Burn";
```

**改进建议**

```c
/* 头文件中仅声明，定义放到实现文件（或直接改为宏）： */
extern const LPCWSTR POLICY_BURN_REGISTRY_PATH;
```

#### 228. `tools/wix314/sdk/inc/polcutil.h:25-28` · 中 / 文档

> `PolcReadString` 通过 `__deref_out_z LPWSTR*` 返回堆上分配的宽字符串，但注释完全没有说明**谁分配、由谁释放、用哪个 API 释放**（CoTaskMemFree / HeapFree / MemFree）。调用方极易漏释放造成泄漏，或使用错误的释放函数导致堆损坏。请在注释中明确所有权与释放方式（并在头文件中提供/指向对应的释放约定）。

**现有代码**

```c
PolcReadString - reads a string from policy.

NOTE: S_FALSE returned if policy not set.
NOTE: out is set to default on S_FALSE or any error.
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 229. `tools/wix314/sdk/inc/polcutil.h:33-34` · 中 / 文档

> `wzDefault` 标注为 `__in_z_opt`（可为 NULL），但注释只说“S_FALSE 或任意错误时 out 置为默认值”，没有说明默认值为 NULL 时 `*pscz` 究竟是 NULL 还是空串 `L""`；同时 `E_OUTOFMEMORY` 等失败路径下输出是否仍保证为默认值也未说明。调用方可能因此对 NULL 解引用，或把“策略未配置”与“读取失败”混为一谈。建议在注释中明确各分支下 `*pscz` 的具体取值，并建议成功时使用 `__deref_out_z`、失败时也统一置 NULL 并让调用方判空。

**现有代码**

```c
    __in_z_opt LPCWSTR wzDefault,
    __deref_out_z LPWSTR* pscz
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 230. `tools/wix314/sdk/inc/polcutil.h:18-19` · 低 / 文档

> `wzPolicyPath` 由调用方以 `__in_z` 直接传入注册表路径，接口本身不约束根键。若实现/调用方传入用户可写位置（HKCU、%ProgramData% 默认可写目录）或受 WOW64/注册表虚拟化重定向影响，被当作安全策略（如是否允许静默安装、是否禁用日志等）读取时可能被低权限用户篡改，形成提权/绕过风险。建议在注释中明确要求使用 HKLM 等可信位置，并在实现侧固定根键、显式指定 KEY_WOW64_64KEY，避免策略被劫持。

**现有代码**

```c
    __in_z LPCWSTR wzPolicyPath,
    __in_z LPCWSTR wzPolicyName,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 231. `tools/wix314/sdk/inc/polcutil.h:1-7` · 低 / 可维护性

> 该头文件使用了 `HRESULT`、`DWORD`、`LPCWSTR`、`LPWSTR`、`DAPI`、`__in_z`/`__out`/`__deref_out_z`/`__in_z_opt` 等 Windows 与 SAL 宏，却未包含任何系统头（如 `windows.h`）或 SAL 定义头，单独包含本文件会编译失败，实际依赖包含顺序的隐式契约。建议显式包含所需头文件（或项目统一的 SAL 定义头），使头文件可独立编译。

**现有代码**

```c
#pragma once
// Copyright (c) .NET Foundation and contributors. All rights reserved. Licensed under the Microsoft Reciprocal License. See LICENSE.TXT file in the project root for full license information.


#ifdef __cplusplus
extern "C" {
#endif
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 232. `tools/wix314/sdk/inc/resrutil.h:1-2` · 低 / 可维护性

> 该头文件未包含任何前置声明（windows.h/dutil.h），却直接使用 HRESULT、LPCWSTR、HINSTANCE、DAPI、SAL 注解等符号，属于“非自包含头文件”。当前仓库中没有任何实现或调用方引用它（全仓库仅此一处出现 ResReadData），一旦被单独 include 会直接编译失败。建议补齐必要的 include（如 <windows.h> 与定义 DAPI 的公共头），或在文件顶部注释明确“必须在包含 dutil.h 之后使用”，避免误用。

**现有代码**

```c
#pragma once
// Copyright (c) .NET Foundation and contributors. All rights reserved. Licensed under the Microsoft Reciprocal License. See LICENSE.TXT file in the project root for full license information.
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 233. `tools/wix314/sdk/inc/resrutil.h:30-31` · 中 / 缺陷

> `__deref_out_bcount(*pcb)` 在 SAL 上引用了 *pcb，但 `pcb` 作为输出参数在下一行才声明，且函数失败时并未约定它会先被赋值。这会让静态分析（如 /analyze 的 C6102）认为读取了未初始化内存；同时失败路径下 ppv/pcb 是否被置 NULL/0 也无约定，调用方很容易在错误分支里对野指针执行释放。建议调整参数顺序（先 `__out DWORD *pcb` 再 `__deref_out_bcount(*pcb) PVOID *ppv`），或使用 `__deref_out_bcount_opt(*pcb)` 并在文档中明确“失败时 *ppv = NULL 且 *pcb = 0，可安全释放”。

**现有代码**

```c
    __deref_out_bcount(*pcb) PVOID *ppv,
    __out DWORD *pcb
```

**改进建议**

```c
    __out DWORD *pcb,
    __deref_out_bcount(*pcb) PVOID *ppv
```

#### 234. `tools/wix314/sdk/inc/resrutil.h:15-19` · 中 / 文档

> 返回值内存的所有权/释放方式未在接口契约中说明：__deref_out_z 表明是调用方持有的新缓冲区，但未说明应使用 LocalFree、HeapFree 还是 SDK 自带的 MemFree/StrFree，二者混用会导致堆损坏或泄漏。同样，资源 ID 不存在、语言回退、字符串超长截断等边界情况应返回什么 HRESULT（如 ERROR_NOT_FOUND / ERROR_INSUFFICIENT_BUFFER）也未约定。建议为 ResReadString/ResReadStringAnsi 增加注释，明确分配器与失败语义。

**现有代码**

```c
HRESULT DAPI ResReadString(
    __in HINSTANCE hinst,
    __in UINT uID,
    __deref_out_z LPWSTR* ppwzString
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 235. `tools/wix314/sdk/inc/resrutil.h:9-13` · 低 / 文档

> wzPath 为 __in_opt，但可选时是改为在当前模块中查找、还是回退到其他语言资源，头文件没有说明；同时 HINSTANCE 为空或模块已卸载时的行为也未定义，调用方可能在句柄失效后继续访问导致崩溃。建议在注释中明确“wzPath == NULL 时仅在 hinst 对应模块中查找”，以及 hinst 的生命周期要求。

**现有代码**

```c
HRESULT DAPI ResGetStringLangId(
    __in_opt LPCWSTR wzPath,
    __in UINT uID,
    __out WORD *pwLangId
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 236. `tools/wix314/sdk/inc/resrutil.h:34-38` · 低 / 安全

> 该接口直接用调用方提供的 wzTargetFile 加 dwCreationDisposition 创建/覆盖文件，头文件未对路径做任何约束说明。若上游路径来自配置或外部输入，可能被用于任意路径写入或覆盖已有文件（如传入 CREATE_ALWAYS 时会静默截断原有文件）。建议在注释中要求实现侧校验路径（拒绝相对路径/.. 穿越、限制在预期目录内），并说明覆盖语义与失败清理（失败时是否删除半成品文件）。

**现有代码**

```c
HRESULT DAPI ResExportDataToFile(
    __in_z LPCSTR szDataName,
    __in_z LPCWSTR wzTargetFile,
    __in DWORD dwCreationDisposition
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 237. `tools/wix314/sdk/inc/rmutil.h:11-14` · 低 / 文档

> 该头文件是 WiX v3.14 SDK 的原样 vendored 头（目录下其余 60+ 个 inc/*.h 风格一致，均不自包含 windows.h/DAPI 定义），当前仓库内没有任何 rmutil 的调用点，因此这里不存在本仓库引入的逻辑缺陷。唯一值得留意的是接口契约未在头中说明：RmuJoinSession 失败时 *ppSession 是否被置 NULL、Add* 失败后是否仍必须调用 RmuEndSession、RmuEndSession 是否允许 NULL/重复调用、以及同一会话能否跨线程并发使用。建议不要就地修改第三方头（会与上游产生分叉），而是在封装层或 README 中补充这些生命周期约定，避免后续调用方漏调用 RmuEndSession 造成 Restart Manager 会话/句柄泄漏。

**现有代码**

```c
HRESULT DAPI RmuJoinSession(
    __out PRMU_SESSION *ppSession,
    __in_z LPCWSTR wzSessionKey
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 238. `tools/wix314/sdk/inc/rexutil.h:16-21` · 高 / 安全

> MEM_FILE 只有 vpStart/uiCurrent/uiLength，没有“已分配容量”字段。内存文件路径在写入前无法判断剩余空间是否足够，一旦从资源解出的数据大于预分配缓冲区，就会直接越界写（缓冲区溢出）。同时 vpStart 声明为 LPCBYTE（const），但内存文件显然要被写入，后续实现必然需要强制转换去掉 const，容易掩盖误用。建议补充容量字段（如 cbCapacity）并明确 vpCurrent 的可写语义。

**现有代码**

```c
struct MEM_FILE 
{
    LPCBYTE vpStart;
    UINT  uiCurrent;
    UINT  uiLength;
};
```

**改进建议**

```c
struct MEM_FILE 
{
    LPBYTE vpStart;
    UINT   cbCapacity;
    UINT   uiCurrent;
    UINT   uiLength;
};
```

#### 239. `tools/wix314/sdk/inc/rexutil.h:26` · 中 / 缺陷

> REX_CALLBACK_WRITE 既没有 pvContext 参数也没有返回值：写入失败/磁盘满/用户取消都无法回传给 RexExtract，导致 RexExtract 可能把“部分写入”的文件当作成功解压；同时缺少上下文使得多个提取任务只能依赖全局状态（如 pFileTable），无法安全并行。建议改为 HRESULT (*)(LPVOID pvContext, UINT cb)，并在 RexExtract 中把非 S_OK 视为中止并触发清理。

**现有代码**

```c
typedef VOID (*REX_CALLBACK_WRITE)(UINT cb);
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 240. `tools/wix314/sdk/inc/rexutil.h:25` · 中 / 缺陷

> REX_CALLBACK_PROGRESS 返回 HRESULT，但头文件未约定返回失败时 RexExtract 的行为（是中止提取并返回该 HRESULT、还是仅记录日志继续）。实现在处理进度回调失败时若继续使用已关闭的句柄/已释放的内存会非常危险。建议在此处显式约定：非 S_OK 即中止提取，并保证已打开的 hFile 关闭、内存文件释放，再透传该 HRESULT。

**现有代码**

```c
typedef HRESULT (*REX_CALLBACK_PROGRESS)(BOOL fBeginFile, LPCWSTR wzFileId, LPVOID pvContext);
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 241. `tools/wix314/sdk/inc/rexutil.h:13` · 中 / 缺陷

> 固定 40 个槽位 + fUsed 复用标记，但接口未约定槽位耗尽的处理方式；若 RexExtract 递归/嵌套（例如回调中再次触发提取）或在多线程下并发调用，会出现槽位竞争、覆盖正在使用的 FAKE_FILE（其 hFile 被关闭或 mfFile 被覆盖）。建议：1) 明确 RexExtract 槽位耗尽时返回失败而非越界；2) 在接口注释中声明该表是否为线程局部/需外部加锁；3) 若支持并发，考虑按调用传递文件表而非全局表。

**现有代码**

```c
#define FILETABLESIZE 40
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 242. `tools/wix314/sdk/inc/rexutil.h:38-39` · 中 / 缺陷

> RexInitialize/RexUninitialize 未约定引用计数与重入语义：RexInitialize 被多次调用是否会清空（并泄漏/悬空）已有文件表？在仍有 RexExtract 执行时调用 RexUninitialize 是否会关闭仍被使用的 hFile？建议在头文件中明确“必须先 Initialize 后 Extract，Extract 期间禁止 Uninitialize”，或改为引用计数式初始化，避免资源泄漏与句柄被并发关闭。

**现有代码**

```c
HRESULT RexInitialize();
void RexUninitialize();
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 243. `tools/wix314/sdk/inc/rexutil.h:5-6` · 中 / 可维护性

> 该头文件不是自包含的：它使用 HRESULT/BOOL/HANDLE/LPCWSTR/LPCBYTE/UINT 以及 __in SAL 注解，但既没有 #include <windows.h> 也没有 <sal.h>（也未统一走 <specstrings.h>），完全依赖调用方先包含 fdi.h 的传递包含顺序，被其他模块单独 include 时可能编译失败。另外 <sys\stat.h> 使用反斜杠路径且本头文件实际未使用 stat 相关符号（若仅为实现需要，应移到 .c 中）。建议显式包含所依赖的头文件并使用正斜杠路径。

**现有代码**

```c
#include <sys\stat.h>
#include <fdi.h>
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 244. `tools/wix314/sdk/inc/pathutil.h:124-126` · 高 / 安全

> 临时文件 API 的安全契约完全缺失，容易导致 TOCTOU 与资源泄漏：
> 1) `dwUniqueCount` 在 GetTempFileName 语义下上限为 0xFFFF，溢出/耗尽时行为未定义，注释应说明取值范围与失败返回；
> 2) 未说明文件是否以独占方式（CREATE_NEW / FILE_SHARE_NONE 或 FILE_FLAG_DELETE_ON_CLOSE、FILE_ATTRIBUTE_TEMPORARY）创建——若实现是「先算名字再 CreateFile」，在共享临时目录下存在可预测命名导致的抢注/符号链接攻击窗口；
> 3) `wzFileNameTemplate` 标了 `__format_string`，却未说明 `dwUniqueCount` 是作为格式参数传入的，调用方传入含 `%s`/不匹配占位符的模板会造成格式串漏洞；
> 4) 两个输出参数都是 `__out_opt`，允许调用方传 NULL/NULL，此时创建出的文件/句柄无人接管而泄漏；且未说明失败时如何清理已创建的文件、句柄由调用方 CloseHandle 还是随 FILE_FLAG_DELETE_ON_CLOSE 自动删除。
> 建议：至少要求一个输出非空，并在注释中写明独占创建、默认 ACL、格式化参数与失败清理约定。

**现有代码**

```c
    __out_opt LPWSTR* psczTempFile,
    __out_opt HANDLE* phTempFile
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 245. `tools/wix314/sdk/inc/pathutil.h:132` · 中 / 安全

> 基于系统时间生成文件名是可预测的（攻击者可枚举/抢先创建同名文件），而声明里没有任何「以独占方式创建、失败即重试」的契约说明。建议在注释中明确要求实现使用 CREATE_NEW/独占共享模式并校验返回值，避免在 %TEMP% 这类多用户可写目录中产生 TOCTOU 或符号链接劫持。

**现有代码**

```c
DAPI_(HRESULT) PathCreateTimeBasedTempFile(
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 246. `tools/wix314/sdk/inc/pathutil.h:29-31` · 中 / 缺陷

> 入参是 `LPCWSTR`（const）却返回可写的 `LPWSTR`：返回的指针指向调用方传入的缓冲区内部，调用者拿到后可能修改本该只读的内存（传入字符串字面量时会直接崩溃），也破坏了 const 正确性。应与 `PathExtension` 一致返回 `LPCWSTR`。

**现有代码**

```c
DAPI_(LPWSTR) PathFile(
    __in_z LPCWSTR wzPath
    );
```

**改进建议**

```c
DAPI_(LPCWSTR) PathFile(
    __in_z LPCWSTR wzPath
    );
```

#### 247. `tools/wix314/sdk/inc/pathutil.h:61-62` · 中 / 缺陷

> SAL 注解弱于实现契约：`__out LPWSTR*` 只表示「写入一个指针」，不表示解引用后得到的字符串已初始化且以 NUL 结尾，因此 /analyze 无法发现「未检查 HRESULT 就使用输出」或「读取未初始化的 *psczFullPath」。本文件其它 API（PathConcat、PathCanonicalizePath、PathCommandLineAppend）都用了 `__deref_out_z`，此处应保持一致。另外 `dwResolveFlags` 是 PATH_EXPAND 的位组合，注释未说明非法位/0 的处理方式（0 是否等价于不做任何展开），调用方容易误用。

**现有代码**

```c
DAPI_(HRESULT) PathExpand(
    __out LPWSTR *psczFullPath,
```

**改进建议**

```c
DAPI_(HRESULT) PathExpand(
    __deref_out_z LPWSTR *psczFullPath,
```

#### 248. `tools/wix314/sdk/inc/pathutil.h:44-46` · 中 / 文档

> 整个头文件没有任何关于输出字符串由哪个分配器分配、调用方如何释放的说明（WiX 中实际为 StrAlloc/ReleaseStr），而 `__deref_out_z`/`LPWSTR*` 参数随处可见。调用方若用 free/delete/CoTaskMemFree 释放会破坏堆；若失败时直接丢弃则泄漏。建议在文件顶部统一说明「所有返回的 LPWSTR 由 StrAlloc 分配，调用方需使用 ReleaseStr 释放；失败时输出是否被置 NULL」的约定，同时把此处的 `__out` 改为 `__deref_out_z`（PathGetParentPath、PathGetKnownFolder 同样问题）。

**现有代码**

```c
DAPI_(HRESULT) PathGetDirectory(
    __in_z LPCWSTR wzPath,
    __out LPWSTR *psczDirectory
```

**改进建议**

```c
DAPI_(HRESULT) PathGetDirectory(
    __in_z LPCWSTR wzPath,
    __deref_out_z LPWSTR *psczDirectory
```

#### 249. `tools/wix314/sdk/inc/pathutil.h:221-224` · 高 / 缺陷

> 该 API 的返回语义与判定规则都未定义，调用方极易误用：
> 1) 返回 HRESULT 但未说明「包含」如何表达（S_OK / S_FALSE 还是别的），也没说明错误（路径不存在、无权访问、规范化失败）与「不包含」的区别——若调用方把 `SUCCEEDED` 当作「包含」，安全检查会直接失效；
> 2) 未声明比较规则：必须按目录边界比较（`C:\foo` 不能匹配 `C:\foobar`）、必须大小写不敏感、必须先规范化（`..`、`.`、8.3 短名、符号链接/重解析点）后再比较，否则可被路径穿越或短名绕过。
> 建议改为返回 `BOOL`（配合 `__out_opt HRESULT*`）或在注释中显式写明上述前提。

**现有代码**

```c
DAPI_(HRESULT) PathDirectoryContainsPath(
    __in_z LPCWSTR wzDirectory,
    __in_z LPCWSTR wzPath
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 250. `tools/wix314/sdk/inc/pathutil.h:71-73` · 中 / 缺陷

> `__inout LPWSTR*` 隐含实现可能重新分配缓冲区（本地路径加 `\\?\`、UNC 加 `\\?\UNC\`，长度会增加），但注释与注解都没有定义重分配失败时的状态：*psczFullPath 是否仍指向原缓冲区？若实现先释放再分配，失败后会留下悬空指针，调用方随后释放即二次释放/野指针。建议改为 `__deref_inout_z`，并明确「失败时 *psczFullPath 保持不变」，同时补充边界（已带 `\\?\` 前缀时是否幂等、根路径、尾随点/空格）。

**现有代码**

```c
DAPI_(HRESULT) PathPrefix(
    __inout LPWSTR *psczFullPath
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 251. `tools/wix314/sdk/inc/pathutil.h:174-176` · 中 / 文档

> 注释「like .NET's Path.Combine」不足以表达实际契约，容易导致调用方逻辑错误：未说明 wzPath2 为绝对路径时是否直接返回 wzPath2（组合还是覆盖）、wzPath1 为 NULL 或空串时的行为、两者都为 NULL 时返回 S_OK 空串还是 E_INVALIDARG、以及拼接时的分隔符与重复 `\` 处理。另外本文件里 `__in_opt` 与 `__in_z_opt` 混用（PathCreateTimeBasedTempFile 用 `__in_z_opt`），建议统一为 `__in_z_opt` 并把上述语义写入注释。

**现有代码**

```c
DAPI_(HRESULT) PathConcat(
    __in_opt LPCWSTR wzPath1,
    __in_opt LPCWSTR wzPath2,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 252. `tools/wix314/sdk/inc/pathutil.h:194-195` · 低 / 文档

> `pnResult` 的取值语义未定义：`CompareStringW` 返回的是 CSTR_LESS_THAN(1)/CSTR_EQUAL(2)/CSTR_GREATER_THAN(3)，调用方若按 `<0 / ==0 / >0` 判断相等会全部走错分支。建议在注释中明确取值常量及「两个路径等价时返回 PtrCmp 结果」的行为。

**现有代码**

```c
DAPI_(HRESULT) PathCompare(
    __in_z LPCWSTR wzPath1,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 253. `tools/wix314/sdk/inc/pathutil.h:1` · 低 / 可维护性

> 该头文件使用了 `DAPI_` 宏以及 HRESULT/LPWSTR/DWORD/HANDLE/HMODULE/BOOL 等 Windows 类型，却既没有包含 `dutil.h`（DAPI_ 定义处）也没有包含 `windows.h`，完全依赖使用者先按特定顺序包含头文件，单独 `#include "pathutil.h"` 会直接编译失败。建议参照同目录的 balutil.h/wcautil.h 补上 `#include "dutil.h"`。

**现有代码**

```c
#pragma once
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 254. `tools/wix314/sdk/inc/procutil.h:10-14` · 中 / 缺陷

> 结构体作为 ProcDisable/RevertWowFileSystemRedirection 的状态载体，但没有任何契约说明：调用方若在栈上声明后未清零，一旦 Disable 中途失败（未写入 pvRevertState），随后调用 Revert 会拿未初始化的 LPVOID 去做 Wow64RevertWow64FsRedirection，属于未定义行为/崩溃；另外重复调用 Revert 也会导致状态错乱。建议在结构体处补充注释，明确“必须先零初始化、仅当 fDisabled 为 TRUE 时在同一线程调用一次 Revert”，并在实现中把 pvRevertState 置空以支持幂等恢复。

**现有代码**

```c
typedef struct _PROC_FILESYSTEMREDIRECTION
{
    BOOL fDisabled;
    LPVOID pvRevertState;
} PROC_FILESYSTEMREDIRECTION;
```

**改进建议**

```c
// 调用方必须先零初始化该结构体（如 { 0 }），且仅当 fDisabled 为 TRUE 时，
// 在调用 Disable 的同一线程上调用一次 Revert，否则句柄/重定向状态会泄漏或错乱。
typedef struct _PROC_FILESYSTEMREDIRECTION
{
    BOOL fDisabled;
    LPVOID pvRevertState;
} PROC_FILESYSTEMREDIRECTION;
```

#### 255. `tools/wix314/sdk/inc/procutil.h:29-31` · 中 / 缺陷

> SAL 方向标注有误：该函数是把 fDisabled/pvRevertState 写回给调用方（输出参数），却标注为 __in。__in 会误导静态分析和调用方使用已初始化但实际被覆盖的结构体，也会掩盖“失败时输出未写入”的问题。应改为 __out（若实现会读取旧值则用 __inout）。同时该 API 修改的是调用线程的 Wow64 重定向状态（线程亲和），建议在注释中写明必须与 ProcRevertWowFileSystemRedirection 在同一线程配对调用，避免跨线程恢复失效。

**现有代码**

```c
HRESULT DAPI ProcDisableWowFileSystemRedirection(
    __in PROC_FILESYSTEMREDIRECTION* pfsr
    );
```

**改进建议**

```c
// 仅影响调用线程的 Wow64 文件系统重定向状态，必须与 ProcRevertWowFileSystemRedirection 在同一线程配对调用。
HRESULT DAPI ProcDisableWowFileSystemRedirection(
    __out PROC_FILESYSTEMREDIRECTION* pfsr
    );
```

#### 256. `tools/wix314/sdk/inc/procutil.h:42-43` · 中 / 缺陷

> wzCommand 只作为输入读取，不应声明为 LPWSTR（非 const）。这样会强制调用方使用可写缓冲区，传字符串字面量在 C++ 下无法编译，也丢失了 const 契约。建议改为 __in_z LPCWSTR。

**现有代码**

```c
HRESULT DAPI ProcExecute(
    __in_z LPWSTR wzCommand,
```

**改进建议**

```c
HRESULT DAPI ProcExecute(
    __in_z LPCWSTR wzCommand,
```

#### 257. `tools/wix314/sdk/inc/procutil.h:39-40` · 中 / 可维护性

> 输出进程句柄的所有权与失败语义未定义：调用方无法从接口判断失败时 *phProcess 是否被置空、成功返回的 HANDLE 应由谁 CloseHandle、以及 hChildStdIn/hChildStdOutErr 是否也可能在部分成功时已创建句柄。这极易造成句柄泄漏或重复关闭。建议补充契约注释（成功时由调用方 CloseHandle，失败时输出置 NULL 且不得留下已打开的句柄），或把失败清理责任显式写入接口说明。

**现有代码**

```c
    __in int nCmdShow,
    __out HANDLE *phProcess
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 258. `tools/wix314/sdk/inc/procutil.h:48-52` · 中 / 文档

> 等待语义与返回码有效性不明确：dwTimeout 为 0 / INFINITE 时的行为、超时是否返回 HRESULT_FROM_WIN32(ERROR_TIMEOUT)（而非 S_OK）、以及 pReturnCode 仅在进程正常结束时才有意义，这些都没有约定。调用方很容易在超时/失败路径上使用未初始化的 *pReturnCode。建议注释说明“pReturnCode 仅在返回 S_OK 时有效，超时返回错误码且不写 pReturnCode”，并考虑对超时单独返回可区分的 HRESULT。

**现有代码**

```c
HRESULT DAPI ProcWaitForCompletion(
    __in HANDLE hProcess,
    __in DWORD dwTimeout,
    __out DWORD *pReturnCode
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 259. `tools/wix314/sdk/inc/procutil.h:64-65` · 中 / 缺陷

> 返回数组的内存所有权未定义：ppdwProcessIds 由谁分配（MemAlloc / CoTaskMemAlloc / new）、调用方应如何释放、失败时是否保证 *ppdwProcessIds = NULL 与 *pcProcessIds = 0 均未说明，存在内存泄漏或错误释放（如对 MemAlloc 内存调用 CoTaskMemFree）的风险。另外按可执行名查找可能命中多个进程，调用方需要同时处理 0 个匹配的情况。建议补充分配/释放约定的注释，并用更精确的 SAL 标注（如 __deref_out_ecount(*pcProcessIds)）。

**现有代码**

```c
HRESULT DAPI ProcFindAllIdsFromExeName(
    __in_z LPCWSTR wzExeName,
```

**改进建议**

```c
// 成功时 *ppdwProcessIds 由 MemAlloc 分配，调用方必须用 MemFree 释放；
// 失败时 *ppdwProcessIds 置 NULL、*pcProcessIds 置 0。
HRESULT DAPI ProcFindAllIdsFromExeName(
    __in_z LPCWSTR wzExeName,
```

#### 260. `tools/wix314/sdk/inc/reswutil.h:19-20` · 中 / 缺陷

> pData 只用了 `__in` 标注，既未声明 const（实现可能误改调用方缓冲区），也没有 `__in_bcount(cbData)` 把缓冲区长度与 cbData 绑定，静态分析（/analyze、CodeQL）无法校验越界读取，传参时也不会在类型层面阻止丢 const。同项目的 fileutil.h:120 已有正确写法可参考（`__in_bcount_opt(cbData) LPCBYTE pbData`）。若允许 cbData==0 且 pData==NULL，应使用 `__in_bcount_opt`。

**现有代码**

```c
    __in PVOID pData,
    __in DWORD cbData
```

**改进建议**

```c
    __in_bcount_opt(cbData) LPCVOID pData,
    __in DWORD cbData
```

#### 261. `tools/wix314/sdk/inc/reswutil.h:24-25` · 低 / 可维护性

> API 不一致：ResWriteString 显式接收 wLangId，而 ResWriteData / ResImportDataFromFile 均无语言参数，调用方无法为 RT_RCDATA/命名资源指定语言，多语言安装包中无法按语言覆盖或区分同名资源。若这是刻意设计（固定写入 neutral/0 语言），请在头文件注释中明确该约定；否则建议补上 `__in WORD wLangId`，避免后续改签名破坏 ABI。

**现有代码**

```c
    __in_z LPCWSTR wzTargetFile,
    __in_z LPCWSTR wzSourceFile,
```

**改进建议**

```c
    __in_z LPCWSTR wzTargetFile,
    __in_z LPCWSTR wzSourceFile,
    __in_z LPCSTR szDataName,
    __in WORD wLangId
```

#### 262. `tools/wix314/sdk/inc/rssutil.h:9-10` · 高 / 缺陷

> 两个释放宏没有用 `do { ... } while (0)` 包裹，存在悬挂 else 问题：`if (cond) ReleaseRssChannel(p); else ...` 会被展开成 `if (cond) if (p) {...}; else ...`，else 会错误地绑定到内层 if。此外：1) `p` 被多次求值，若传入带副作用的表达式（如 `arr[i++]`、`GetChannel()`）会重复求值；2) `ReleaseRssChannel` 释放后不清空指针，调用方继续使用即悬空指针/重复释放；3) 宏参数未加括号保护。建议改为 do/while 形式并对参数加括号。

**现有代码**

```c
#define ReleaseRssChannel(p) if (p) { RssFreeChannel(p); }
#define ReleaseNullRssChannel(p) if (p) { RssFreeChannel(p); p = NULL; }
```

**改进建议**

```c
#define ReleaseRssChannel(p)     do { if (p) { RssFreeChannel(p); (p) = NULL; } } while (0)
#define ReleaseNullRssChannel(p) do { if (p) { RssFreeChannel(p); (p) = NULL; } } while (0)
```

#### 263. `tools/wix314/sdk/inc/rssutil.h:1` · 中 / 可维护性

> 头文件不自治：本文件使用了 `LPWSTR`、`LPCWSTR`、`DWORD`、`FILETIME`、`HRESULT`、`DAPI`、`__in_z`/`__out` 等类型与 SAL 注解，但没有任何 `#include`（如 `<windows.h>`、WiX 的 `specstrings.h`/`dutil.h`）。能否编译完全依赖调用方的 include 顺序，一旦被单独包含或顺序不同就会报未定义类型。建议在文件头部显式包含所需依赖（或用 `#error` 做前置检查）。

**现有代码**

```c
#pragma once
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 264. `tools/wix314/sdk/inc/rssutil.h:57-58` · 高 / 缺陷

> `rgItems[1]` + `cItems` 的变长结构缺少分配契约说明与溢出约束：正确分配大小为 `sizeof(RSS_CHANNEL) + (cItems - 1) * sizeof(RSS_ITEM)`，当解析不可信 RSS 得到超大条目数时，该乘法若在 32 位下以 `size_t`/`DWORD` 计算会整数溢出，导致堆分配过小并在写入第 cItems 个元素时越界；同时 `cItems == 0` 时结构体仍保留 1 个元素，计数语义与 SAL 数组长度不一致。建议在注释中写明分配公式并要求实现方对 `cItems` 显式上限校验（如 `cItems > (MAXDWORD - sizeof(RSS_CHANNEL)) / sizeof(RSS_ITEM)` 时失败），否则任何调用方都容易误算。

**现有代码**

```c
    DWORD cItems;
    RSS_ITEM rgItems[1];
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 265. `tools/wix314/sdk/inc/rssutil.h:82-84` · 中 / 缺陷

> `__in_xcount(pChannel->cItems)` 在 `pChannel` 为 NULL 时本身就是一次解引用（静态分析/运行时若启用 xcount 校验会读到空指针成员的偏移），而 `ReleaseRssChannel` 恰恰允许传入 `NULL`；同时该注解只描述了元素个数，未表达指针不可为空或函数允许 NULL 的语义。另外上面的 `#ifndef __in_xcount` 空宏会静默吞掉 SAL 注解，使后续所有 `__in_xcount` 校验失效。建议为 `pChannel` 增加 `__in_opt`（配合 xcount 使用 `__in_xcount_opt`）或明确要求非空，并避免用空宏兜底 SAL。

**现有代码**

```c
void DAPI RssFreeChannel(
    __in_xcount(pChannel->cItems) RSS_CHANNEL *pChannel
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 266. `tools/wix314/sdk/inc/rssutil.h:67-70` · 中 / 文档

> 所有权的释放契约未写明：`RSS_CHANNEL`/`RSS_ITEM` 中的全部 `LPWSTR` 字段（wzTitle/wzLink/wzDescription/wzGuid/wzEnclosureUrl/wzEnclosureType）以及 `pUnknownElements`、`RSS_UNKNOWN_ELEMENT::pAttributes` 两条链表都必须由 `RssFreeChannel` 递归释放，调用方不得逐个 free；但头文件对此只字未提，极易造成调用方自行 free 字符串（双重释放）或只释放顶层结构（内存泄漏）。建议为结构体和 `RssFreeChannel` 补充注释，明确“整体所有权归 `RssFreeChannel`”这一唯一释放入口。

**现有代码**

```c
HRESULT DAPI RssParseFromString(
    __in_z LPCWSTR wzRssString,
    __out RSS_CHANNEL **ppChannel
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 267. `tools/wix314/sdk/inc/rssutil.h:72-75` · 中 / 安全

> `RssParseFromString`/`RssParseFromFile` 直接处理外部不可信 RSS：建议在接口契约中明确 (1) 失败时必须把 `*ppChannel` 置为 NULL，避免调用方用未初始化/半成品指针去 `ReleaseRssChannel` 而崩溃；(2) 输入为 NULL 或空串时的行为；(3) 解析器需禁用外部实体/DTD（XXE、实体膨胀）并对输入长度与节点数量设置上限，防止超大负载耗尽内存。这些约束若不在头文件中固化，各调用点很容易各自假设而导致漏洞。

**现有代码**

```c
HRESULT DAPI RssParseFromFile(
    __in_z LPCWSTR wzRssFile,
    __out RSS_CHANNEL **ppChannel
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 268. `tools/wix314/sdk/inc/rssutil.h:61-62` · 低 / 文档

> `RssInitialize`/`RssUninitialize` 暗示存在全局解析器状态（及可能的一次性 XML 库初始化），但头文件未说明：是否必须在任何 Parse 之前调用、重复初始化的语义、未初始化直接 Parse 的行为，以及多线程并发调用 Parse/Free 时的线程安全保证。建议补充生命周期与线程安全约定，避免调用方在 DllMain 或多线程场景下误用。

**现有代码**

```c
HRESULT DAPI RssInitialize(
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 269. `tools/wix314/sdk/inc/regutil.h:10` · 中 / 缺陷

> ReleaseRegKey 宏有三个隐患：1) 参数 h 被求值两次（if 判断 + 赋值），传入带副作用的表达式（如 pKeys[i++] 或返回句柄的函数调用）会导致重复关闭或写出到错误位置；2) 未用 do { } while (0) 包裹，在 `if (ok) ReleaseRegKey(h); else ...` 场景中会破坏 else 的配对并可能引发悬垂/重复关闭；3) 按本目录约定（ReleaseX 不置空、ReleaseNullX 置空）该宏行为与命名不符，调用方容易误以为拿到的是非置空语义。

**现有代码**

```c
#define ReleaseRegKey(h) if (h) { ::RegCloseKey(h); h = NULL; }
```

**改进建议**

```c
#define ReleaseRegKey(h) do { HKEY RegUtil_hTmp = (h); if (RegUtil_hTmp) { ::RegCloseKey(RegUtil_hTmp); (h) = NULL; } } while (0)
```

#### 270. `tools/wix314/sdk/inc/regutil.h:114-115` · 中 / 缺陷

> PFN_REGDELETEKEYW 在上面已声明，但 RegFunctionOverride 的参数列表里没有对应槽位（同时也缺少 PFN_REGCLOSEKEY* 之类的关闭钩子）。结果是：该 typedef 成为死代码；RegDelete 在删除叶子键时若内部直接调用 ::RegDeleteKeyW，则这条路径无法像其它 API 一样被测试/兼容层替换，与整个“全局函数指针可注入”的设计不一致。建议补充 __in_opt PFN_REGDELETEKEYW pfnRegDeleteKeyW 参数。

**现有代码**

```c
    __in_opt PFN_REGDELETEVALUEW pfnRegDeleteValueW
    );
```

**改进建议**

```c
    __in_opt PFN_REGDELETEVALUEW pfnRegDeleteValueW,
    __in_opt PFN_REGDELETEKEYW pfnRegDeleteKeyW
    );
```

#### 271. `tools/wix314/sdk/inc/regutil.h:102-103` · 中 / 缺陷

> RegInitialize/RegUninitialize 没有引用计数，RegFunctionOverride 又直接改写全局函数指针且无任何同步：多线程场景下（例如后台线程正在 RegOpen 时切换/卸载注入实现）可能读到被半写或已被 Uninitialize 重置的函数指针，导致空指针调用或调用已卸载模块的代码；重复 Initialize/Uninitialize 也会互相破坏状态。建议要么在注释中明确“必须在任何工作线程启动前完成初始化/覆盖，且不可在运行期卸载”，要么用 SRWLOCK/InterlockedExchangePointer + 引用计数实现安全切换。另外在 C 语言下 `()` 表示参数未指定，建议写成 `(void)` 以获得原型检查。

**现有代码**

```c
HRESULT DAPI RegInitialize();
void DAPI RegUninitialize();
```

**改进建议**

```c
HRESULT DAPI RegInitialize(void);
void DAPI RegUninitialize(void);
```

#### 272. `tools/wix314/sdk/inc/regutil.h:205-206` · 中 / 缺陷

> SAL 计数表达式用的 cValues 与形参名 cStrings 不一致，静态分析无法把缓冲区长度关联到真实参数（通常报 28252/未知注解），真实边界契约被掩盖；一旦后续有人改了参数名而没同步注解，编译器/分析器也不会报错。另外该参数是只读输入，理想情况下应为 `const LPWSTR*`（因指针到指针的 const 转换在 C++ 调用点不成立，此项可按项目习惯保留 LPWSTR*，但至少计数名必须修正）。

**现有代码**

```c
    __in_ecount(cValues) LPWSTR *rgwzStrings,
    __in DWORD cStrings
```

**改进建议**

```c
    __in_ecount(cStrings) LPWSTR *rgwzStrings,
    __in DWORD cStrings
```

#### 273. `tools/wix314/sdk/inc/regutil.h:173` · 低 / 缺陷

> 计数取自输出参数 pcStrings 本身，而不是 `*pcStrings`；调用点上 pcStrings 指向的内容尚未初始化，函数入口处该注解值无意义，PREfast 无法据此校验写入的元素个数（本目录 wiutil.h/iniutil.h 沿用了同样写法，属于既有约定问题）。建议写成 `__deref_out_ecount_opt(*pcStrings)`，并在该 API 上说明数组及每个字符串由调用方用 MemFree/ReleaseStr 释放、失败时是否置空/置 0。

**现有代码**

```c
    __deref_out_ecount_opt(pcStrings) LPWSTR** prgsczStrings,
```

**改进建议**

```c
    __deref_out_ecount_opt(*pcStrings) LPWSTR** prgsczStrings,
```

#### 274. `tools/wix314/sdk/inc/regutil.h:137-140` · 中 / 可维护性

> 只有 RegDelete 接受 REG_KEY_BITNESS，而 RegCreate/RegCreateEx/RegOpen 没有对应参数（调用方只能自行把 KEY_WOW64_32KEY/64KEY 混进 dwAccess）。这使同一套 API 对 WOW64 注册表视图的语义不一致，容易出现“在 32 位视图创建、在 64 位视图删除”的错配，且 RegDelete 中 kbKeyBitness 到 samDesired 的映射规则在头文件中没有任何说明。建议统一各入口的 bitness 参数，或至少在注释中明确 dwAccess 必须自带 WOW64 标志、kbKeyBitness 仅对删除生效。

**现有代码**

```c
HRESULT DAPI RegDelete(
    __in HKEY hkRoot,
    __in_z LPCWSTR wzSubKey,
    __in REG_KEY_BITNESS kbKeyBitness,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 275. `tools/wix314/sdk/inc/regutil.h:127` · 低 / 可维护性

> 同一个契约存在两种签名：PFN_REGCREATEKEYEXW 使用的是 `CONST LPSECURITY_ATTRIBUTES`，而 RegCreateEx 用的是可写的 SECURITY_ATTRIBUTES*。这既不一致，也让持有 const 安全属性结构的调用方无法直接复用（需要强制转换）。建议统一为 const。

**现有代码**

```c
    __in_opt SECURITY_ATTRIBUTES* pSecurityAttributes,
```

**改进建议**

```c
    __in_opt const SECURITY_ATTRIBUTES* pSecurityAttributes,
```

#### 276. `tools/wix314/sdk/inc/shelutil.h:22-24` · 中 / 可维护性

> `ShelExec` 的可选字符串参数使用 `__in_opt`，而同文件里 `ShelExecUnelevated` 的同类参数使用 `__in_z_opt`。`__in_opt` 不包含"以 null 结尾"的语义契约，静态分析（/analyze、SAL）无法发现传入非 null 结尾缓冲区的问题，且两套 API 的注解不一致易误用。建议统一为 `__in_z_opt`。

**现有代码**

```c
    __in_opt LPCWSTR wzParameters,
    __in_opt LPCWSTR wzVerb,
    __in_opt LPCWSTR wzWorkingDirectory,
```

**改进建议**

```c
    __in_z_opt LPCWSTR wzParameters,
    __in_z_opt LPCWSTR wzVerb,
    __in_z_opt LPCWSTR wzWorkingDirectory,
```

#### 277. `tools/wix314/sdk/inc/shelutil.h:27-28` · 中 / 文档

> `phProcess` 的生命周期语义未声明：调用方无法从接口判断 (1) 失败时 `*phProcess` 是否会被置空/保持未初始化（当前为 `__out_opt`，若实现失败路径不写入，调用方读取未初始化局部变量即为未定义行为）；(2) 成功时谁负责 `CloseHandle`（Shell 返回的 hProcess 调用方必须自行关闭，否则每个启动操作都会泄漏一个句柄）。请在头文件中显式约定：成功时返回调用方需 `CloseHandle` 的句柄，失败时置为 NULL，并要求调用方初始化为 NULL。

**现有代码**

```c
    __out_opt HANDLE* phProcess
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 278. `tools/wix314/sdk/inc/shelutil.h:37-39` · 中 / 文档

> `ShelGetFolder` 通过 `LPWSTR*` 输出路径，但未说明分配方式与释放责任（是 StrAlloc/CoTaskMemAlloc/HeapAlloc？应使用 StrFree/CoTaskMemFree/HeapFree？）。调用方在不知道分配器的情况下无法正确释放，最坏结果是堆破坏（用错 free）或稳定泄漏。建议在声明处注释释放方式，并明确失败时 `*psczFolderPath` 不被修改（调用方应先置 NULL）。另外 `csidlFolder` 建议注明只接受 CSIDL_* 常量且该 API 已废弃、新代码应优先使用 `ShelGetKnownFolder`。

**现有代码**

```c
    __out_z LPWSTR* psczFolderPath,
    __in int csidlFolder
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 279. `tools/wix314/sdk/inc/shelutil.h:41-43` · 中 / 文档

> `ShelGetKnownFolder` 同样缺少输出缓冲区所有权说明（`SHGetKnownFolderPath` 返回的是 CoTaskMemAlloc 内存，需要 `CoTaskMemFree`），且未声明运行期依赖：`SHGetKnownFolderPath` 仅在 Windows Vista 及以上存在，而本头文件通过 `REFKNOWNFOLDERID -> REFGUID` 的降级让任何 SDK 都能编译通过，调用方在 XP 上会得到"链接/加载成功但运行失败"。建议补充注释说明释放方式与最低支持系统（或加 `#if NTDDI_VERSION >= NTDDI_VISTA` 之类的版本守卫）。

**现有代码**

```c
    __out_z LPWSTR* psczFolderPath,
    __in REFKNOWNFOLDERID rfidFolder
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 280. `tools/wix314/sdk/inc/shelutil.h:17-19` · 中 / 缺陷

> `ShelFunctionOverride` 直接覆盖全局的 `ShellExecuteExW` 函数指针，但头文件未声明线程安全与恢复语义：并发调用 `ShelExec`/`ShelExecUnelevated` 与 `ShelFunctionOverride` 会构成数据竞争（非原子读写函数指针），并可能出现重入（覆盖的函数自身再调用 `ShelExec`）。建议在注释中明确"必须在任何 Shell 执行发生前、单线程初始化阶段调用；传 NULL 恢复原函数"，或在实现中改用原子交换/一次性初始化来保证可见性。

**现有代码**

```c
void DAPI ShelFunctionOverride(
    __in_opt PFN_SHELLEXECUTEEXW pfnShellExecuteExW
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 281. `tools/wix314/sdk/inc/shelutil.h:29` · 中 / 安全

> `ShelExecUnelevated` 会把 `wzTargetPath`/`wzParameters`/`wzWorkingDirectory` 直接交给 Shell 执行，且刻意绕过提权。若这些参数来自不可信输入（安装包属性、用户可控配置文件、临时目录中的可执行文件），则可被用于启动任意命令（参数注入）或从可写的当前目录/工作目录加载 DLL/程序（二进制劫持）。建议在注释中写明安全契约：仅接受由可信来源构造的绝对路径，禁止把未校验的外部数据拼进参数或工作目录；必要时在实现中校验路径的规范化与文件 ACL。

**现有代码**

```c
HRESULT DAPI ShelExecUnelevated(
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 282. `tools/wix314/sdk/inc/sqlutil.h:31-37` · 中 / 缺陷

> SAL 契约与调用方式矛盾：当 fIntegratedAuth 为 TRUE 时，wzUser/wzPassword 通常传 NULL，但这里标注为 `__in_z`（必填且以 NUL 结尾），调用方传 NULL 会触发 PREfast/C6102 告警，并在实现内部存在解引用风险。同样的签名在 SqlDatabaseExists / SqlDatabaseEnsureExists / SqlCreateDatabase / SqlDropDatabase 中重复出现，需一并修改。
>
> 另外凭据以裸 `LPCWSTR` 传递，建议在头文件注释中明确要求：实现方不得把 wzPassword 拼接进错误描述/日志（pbstrErrorDescription 会回流给调用方与日志），并在用完后清零临时缓冲区，避免密码泄漏。

**现有代码**

```c
HRESULT DAPI SqlConnectDatabase(
    __in_z LPCWSTR wzServer, 
    __in_z LPCWSTR wzInstance,
    __in_z LPCWSTR wzDatabase, 
    __in BOOL fIntegratedAuth, 
    __in_z LPCWSTR wzUser, 
    __in_z LPCWSTR wzPassword, 
```

**改进建议**

```c
HRESULT DAPI SqlConnectDatabase(
    __in_z LPCWSTR wzServer, 
    __in_opt_z LPCWSTR wzInstance,
    __in_z LPCWSTR wzDatabase, 
    __in BOOL fIntegratedAuth, 
    __in_opt_z LPCWSTR wzUser, 
    __in_opt_z LPCWSTR wzPassword, 
```

#### 283. `tools/wix314/sdk/inc/sqlutil.h:20-27` · 中 / 可维护性

> SQL_FILESPEC 的定长缓冲区契约未定义，存在截断/越界风险：
> 1) wzSize/wzMaxSize/wzGrow 存放的是 "10MB" 这类大小规格串，却复用了 MAX_PATH(260)，属于复制粘贴，缓冲区语义与实际用途不符；
> 2) 结构体没有配套的 cch 长度字段，也没有说明必须 NUL 结尾、实现方需对超长输入做校验（否则 strsafe 拷贝会被截断成非法 T-SQL，或实现方若用 wcscpy 则越界）；
> 3) 无法区分“未设置”与“空串”（调用方常以 zero-init 表示未设置但没有显式约定）。
> 建议为各字段定义专用长度常量（如 SQL_FILESPEC_NAME_MAX/SIZE_MAX），并在注释中写明 NUL 结尾与长度校验要求。

**现有代码**

```c
struct SQL_FILESPEC
{
    WCHAR wzName[MAX_PATH];
    WCHAR wzFilename[MAX_PATH];
    WCHAR wzSize[MAX_PATH];
    WCHAR wzMaxSize[MAX_PATH];
    WCHAR wzGrow[MAX_PATH];
};
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 284. `tools/wix314/sdk/inc/sqlutil.h:120-125` · 中 / 缺陷

> 输出参数契约与 SqlSessionExecuteQuery 不一致：这里 `ppirs`/`pcRows` 标注为 `__out`（不可为 NULL），而 SqlSessionExecuteQuery 中同语义的参数是 `__out_opt`。这会让只想取影响行数（或只想取行集）的调用方被迫传入无用的哑指针，且静态分析无法发现实现里对 `*ppirs`/`*pcRows` 的可选处理。请统一为 `__out_opt`，并在注释中说明：非行集语句（如 CREATE/ALTER）时 `*ppirs` 是否置 NULL、`*pcRows` 是否有效。

**现有代码**

```c
HRESULT DAPI SqlCommandExecuteQuery(
    __in IDBCreateCommand* pidbCommand, 
    __in __sql_command LPCWSTR wzSql, 
    __out IRowset** ppirs,
    __out DBROWCOUNT* pcRows
    );
```

**改进建议**

```c
HRESULT DAPI SqlCommandExecuteQuery(
    __in IDBCreateCommand* pidbCommand, 
    __in __sql_command LPCWSTR wzSql, 
    __out_opt IRowset** ppirs,
    __out_opt DBROWCOUNT* pcRows
    );
```

#### 285. `tools/wix314/sdk/inc/sqlutil.h:126-127` · 中 / 文档

> 多个接口通过 `__out_opt BSTR*` / `__out BSTR` 输出错误描述，但整个头文件没有约定所有权：调用方必须 SysFreeString，且失败路径下 `*pbstr` 是否被置 NULL（是否已分配）也没有说明——这正是 BSTR 重复释放/泄漏的典型来源。建议在文件头或 SqlGetErrorInfo 处统一声明：所有 BSTR 输出均由 callee 通过 SysAllocString 分配、caller 负责 SysFreeString，且函数入口会先置 *pbstr = NULL（即使返回失败也可能带错误串）。

**现有代码**

```c
HRESULT DAPI SqlGetErrorInfo(
    __in IUnknown* pObjectWithError,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 286. `tools/wix314/sdk/inc/sqlutil.h:45-48` · 低 / 文档

> 事务 API 的失败语义未定义：SqlEndTransaction 只用 BOOL 决定提交还是回滚，没有说明提交失败后 pit 的状态与释放责任（是 callee 内部 Abort 并仍由 caller Release，还是 baulk 后事务已失效？），也没有说明回滚失败时的返回值策略。这直接影响调用方在异常路径上是否会泄漏 ITransaction（SqlStartTransaction 同时输出 IDBCreateCommand 和 ITransaction，两者都需 Release）。建议在注释中写明所有权/释放规则和失败后的数据一致性保证，并用枚举替代裸 BOOL 以提升可读性。

**现有代码**

```c
HRESULT DAPI SqlEndTransaction(
    __in ITransaction* pit,
    __in BOOL fCommit
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 287. `tools/wix314/sdk/inc/sqlutil.h:49-50` · 低 / 文档

> 存在性检查的 HRESULT 语义未约定：未说明“数据库不存在”是以 S_FALSE 还是失败码返回（调用方若用 FAILED(hr) 判断会把“不存在”误判为致命错误），也未说明此时 pbstrErrorDescription 是否会被填充。四个 *Exists/*EnsureExists 接口都需补充该契约。

**现有代码**

```c
HRESULT DAPI SqlDatabaseExists(
    __in_z LPCWSTR wzServer,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 288. `tools/wix314/sdk/inc/sceutil.h:22-23` · 高 / 缺陷

> 释放宏未使用 do { ... } while (0) 包裹，也未对宏体加花括号隔离：在无花括号的 if/else 中展开时会产生悬垂 else（如 `if (x) ReleaseSceRow(h); else ...` 会编译失败或语义改变）；同时参数 `prrh` 在宏体中被求值两次（if 判断 + 调用），若传入带副作用的表达式（如 `arr[i++]`）行为不可预期。建议统一改为 do-while 形式并只求值一次（先赋值到局部变量）。注意 ReleaseNullSceRow 的赋值也应针对原始左值，因此实现时需保留 `prrh = NULL`。

**现有代码**

```c
#define ReleaseSceRow(prrh) if (prrh) { SceFreeRow(prrh); }
#define ReleaseNullSceRow(prrh) if (prrh) { SceFreeRow(prrh); prrh = NULL; }
```

**改进建议**

```c
#define ReleaseSceRow(prrh) do { if (prrh) { SceFreeRow(prrh); } } while (0)
#define ReleaseNullSceRow(prrh) do { if (prrh) { SceFreeRow(prrh); (prrh) = NULL; } } while (0)
```

#### 289. `tools/wix314/sdk/inc/sceutil.h:203-204` · 高 / 缺陷

> `SCE_QUERY_BYTES` 在本头文件中从未声明（只有 `SCE_QUERY_HANDLE_BYTES`，见第 18-20 行），全仓库搜索也仅出现在这些 SAL 注解里；同理 `SCE_QUERY_RESULTS_BYTES` 也未定义（第 237、240、256 行）。普通编译下 SAL 宏展开为空可能不报错，但 /analyze 或启用 SAL 静态分析时会因未定义标识符而报错，且这些 bcount 约束实际失效，无法发现句柄缓冲区越界。请统一改用已声明的 `SCE_QUERY_HANDLE_BYTES` / `SCE_QUERY_RESULTS_HANDLE_BYTES`（或补充对应常量定义）。

**现有代码**

```c
HRESULT DAPI SceSetQueryColumnBinary(
    __in_bcount(SCE_QUERY_BYTES) SCE_QUERY_HANDLE sqhHandle,
```

**改进建议**

```c
HRESULT DAPI SceSetQueryColumnBinary(
    __in_bcount(SCE_QUERY_HANDLE_BYTES) SCE_QUERY_HANDLE sqhHandle,
```

#### 290. `tools/wix314/sdk/inc/sceutil.h:224-225` · 严重 / 缺陷

> 该查询列设置器的句柄类型写错了：参数声明为 `SCE_ROW_HANDLE rowHandle`（并按 SCE_ROW_HANDLE_BYTES 约束），与其它 SetQueryColumn 系列统一使用的 `SCE_QUERY_HANDLE` 不一致。调用方按 API 语义传入查询句柄时，实现侧会把它当作行句柄解释，极易造成结构体字段错位/越界写（内存破坏）。请改为 `__in_bcount(SCE_QUERY_HANDLE_BYTES) SCE_QUERY_HANDLE sqhHandle` 并与实现同步。

**现有代码**

```c
HRESULT DAPI SceSetQueryColumnSystemTime(
    __in_bcount(SCE_ROW_HANDLE_BYTES) SCE_ROW_HANDLE rowHandle,
```

**改进建议**

```c
HRESULT DAPI SceSetQueryColumnSystemTime(
    __in_bcount(SCE_QUERY_HANDLE_BYTES) SCE_QUERY_HANDLE sqhHandle,
```

#### 291. `tools/wix314/sdk/inc/sceutil.h:231-232` · 中 / 缺陷

> `psqhHandle` 是“指向句柄的指针”，不是字节缓冲区，用 `__in_bcount(...)` 注解在语义上是错误的（且 SCE_QUERY_BYTES 未定义）：静态分析会把指针目标当作 N 字节的只读缓冲区，既无法表达“执行后句柄被释放”的所有权转移，也可能误报/漏报。建议改为 `__in`（或 `__inout`/`__deref_in` 视实现而定），并在注释中明确该调用会消耗/释放查询句柄，避免调用方再调用 SceFreeQuery 造成双重释放。第 236 行 SceRunQueryRange 存在同样问题。

**现有代码**

```c
HRESULT DAPI SceRunQueryExact(
    __in_bcount(SCE_QUERY_BYTES) SCE_QUERY_HANDLE *psqhHandle,
```

**改进建议**

```c
HRESULT DAPI SceRunQueryExact(
    __in SCE_QUERY_HANDLE *psqhHandle,
```

#### 292. `tools/wix314/sdk/inc/sceutil.h:169-170` · 中 / 文档

> `SceGetColumnBinary` 的输出缓冲区所有权未文档化：`ppbBuffer` 由谁分配、调用方应使用 `free`/`HeapFree`/`CoTaskMemFree` 还是某个专用释放函数，输入时 `*pcbBuffer` 是容量还是返回值，缓冲区不足时返回什么错误（是否需要两阶段调用）都没有说明。同类的 `SceGetColumnString` 的 `psczValue`（第 188-190 行）也一样。缺失契约会导致调用方泄漏或误用错误释放器，建议在声明处补充注释明确分配器与释放方式，并考虑为返回缓冲区提供配套的释放 API。

**现有代码**

```c
    __out_opt BYTE **ppbBuffer,
    __inout SIZE_T *pcbBuffer
```

**改进建议**

```c
    // ppbBuffer: 由 SCEUtil 分配，调用方使用 SceFreeBuffer/CoTaskMemFree 释放
    // pcbBuffer: 入参为缓冲区容量，出参为实际所需/已写入字节数
    __out_opt BYTE **ppbBuffer,
    __inout SIZE_T *pcbBuffer
```

#### 293. `tools/wix314/sdk/inc/sceutil.h:60-63` · 中 / 文档

> 结构体把内部 COM 接口指针 `pIRowset` / `pIRowsetChange` 直接暴露给使用者，但头文件未声明任何线程安全或生命周期约定：这些接口是 STA/COM 对象的引用，若数据库对象被多个线程共享（或使用者在未持有事务时直接调用），会出现数据竞争与释放后使用；`SceCloseDatabase` 释放这些接口后，外部仍持有的 `SCE_TABLE_SCHEMA*` / `SCE_DATABASE*` 也立刻变成悬垂指针。建议在头文件中明确“非线程安全、不可跨线程共享、只能通过 SCEUtil API 访问”的约束，或按 TODO 用不透明句柄隐藏内部指针。

**现有代码**

```c
    // Internal to SCEUtil - consumers shouldn't access or modify
    // TODO: enforce / hide in a handle of some sort?
    IRowset *pIRowset;
    IRowsetChange *pIRowsetChange;
```

**改进建议**

```c
    // Internal to SCEUtil - consumers shouldn't access or modify
    // SCEUTIL is not thread-safe: a SCE_DATABASE must not be shared across threads.
    // These interfaces are owned by SCEUtil and invalidated by SceCloseTable/SceCloseDatabase.
    IRowset *pIRowset;
    IRowsetChange *pIRowsetChange;
```

#### 294. `tools/wix314/sdk/inc/sceutil.h:243-248` · 中 / 可维护性

> `SceCloseDatabase` 以 `SCE_DATABASE *` 传参，从命名与 `__deref_out` 创建配对关系看，它很可能还会释放数据库结构本身；但函数签名无法把调用方的指针置空，调用方在关闭后继续使用同一指针（或其内部的 schema/表指针）就会 UAF，且错误重复关闭时也缺少防御。建议要么改为接收 `SCE_DATABASE **ppDatabase`（关闭并置空），要么在注释中明确“调用后 pDatabase 及其 schema 全部失效，调用方不得再次引用”；`SceCloseTable` 同理。

**现有代码**

```c
void DAPI SceCloseTable(
    __in SCE_TABLE_SCHEMA *pTable
    );
HRESULT DAPI SceCloseDatabase(
    __in SCE_DATABASE *pDatabase
    );
```

**改进建议**

```c
void DAPI SceCloseTable(
    __in SCE_TABLE_SCHEMA *pTable
    );
// 调用后 pDatabase 及其 schema 全部失效，调用方不得再次引用
HRESULT DAPI SceCloseDatabase(
    __in SCE_DATABASE *pDatabase
    );
```

#### 295. `tools/wix314/sdk/inc/wcalog.h:9` · 中 / 缺陷

> 头文件自包含性问题：本文件直接使用 `WIXAPI`、`BOOL`、`HRESULT`，但既未包含任何声明它们的头文件（`WIXAPI` 实际只在 `wcautil.h` 中 `#define WIXAPI __stdcall`，`BOOL/HRESULT` 来自 windows.h），也未提供 `#ifndef WIXAPI` 兜底定义。若调用方先包含本头文件（或包含顺序与 wcautil.h 相反），预处理后 `WIXAPI` 会被当作未声明标识符，导致 "syntax error: missing ';' before 'IsVerboseLogging'" 之类的编译错误。建议在 `extern "C"` 块之前显式包含定义这些类型的头（如 `#include "wcautil.h"`，其内部已定义 WIXAPI 并引入 windows.h），或至少加上 `#ifndef WIXAPI / #define WIXAPI __stdcall / #endif` 保护，使头文件不依赖调用方的包含顺序。

**现有代码**

```c
BOOL WIXAPI IsVerboseLogging();
```

**改进建议**

```c
#include "wcautil.h"

#ifdef __cplusplus
extern "C" {
#endif

BOOL WIXAPI IsVerboseLogging();
```

#### 296. `tools/wix314/sdk/inc/wcalog.h:10` · 低 / 文档

> 接口契约缺少必要说明：`SetVerboseLoggingAtom` 名称中的 "Atom" 暗示底层通过 Atom 表实现原子/进程级共享状态，但没有任何注释说明该状态的作用域（进程内是否跨线程/跨模块可见）、多线程并发调用是否安全、以及何时/如何重置。同时 `IsVerboseLogging` 只返回 `BOOL` 而无错误通道，调用方无法区分“查询失败”与“verbose 关闭”。建议补充注释明确：1）线程安全性与可见性语义；2）`SetVerboseLoggingAtom` 返回的 HRESULT 失败情形（例如 Atom 分配失败）；3）状态生命周期（是否需在 DllMain/卸载时释放），避免后续维护与测试误用。

**现有代码**

```c
HRESULT WIXAPI SetVerboseLoggingAtom(BOOL bValue);
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 297. `tools/wix314/sdk/inc/srputil.h:1-2` · 高 / 缺陷

> 头文件不自包含：本文件使用了 `DAPI_`、`HRESULT`、`BOOL`、`LPCWSTR` 以及 SAL 注解 `__in`/`__in_z`，但没有包含任何提供这些定义的头文件（`DAPI_` 定义在 dutil.h 第 8 行 `#define DAPI_(type) EXTERN_C type DAPI`）。同目录下的 balutil.h（第 5 行 `#include "dutil.h"`）、pathutil.h 等均显式包含 dutil.h。当前若调用方按字母序或单独先包含 srputil.h（如 `#include "srputil.h"` 置于其他 wix 头之前、或未包含 windows.h/预编译头），会出现 `DAPI_` 未定义、`HRESULT`/`LPCWSTR` 未知类型等编译错误。建议与同目录头文件保持一致，在 extern "C" 之前加入 `#include "dutil.h"`。

**现有代码**

```c
#pragma once
// Copyright (c) .NET Foundation and contributors. All rights reserved. Licensed under the Microsoft Reciprocal License. See LICENSE.TXT file in the project root for full license information.
```

**改进建议**

```c
#pragma once
// Copyright (c) .NET Foundation and contributors. All rights reserved. Licensed under the Microsoft Reciprocal License. See LICENSE.TXT file in the project root for full license information.


#include "dutil.h"
```

#### 298. `tools/wix314/sdk/inc/srputil.h:31` · 低 / 缺陷

> `SrpUninitialize()` 使用了空参数列表。在 C 语言中这表示「参数未指定」而非「无参数」，调用方传入任意实参也能通过编译（且 C23 前不会报诊断），容易掩盖误用；同时它也没有体现与 `SrpInitialize` 的配对契约（重复 Uninitialize、未 Initialize 即调用、多线程并发初始化的行为未定义）。建议改为 `void` 形参并在注释中说明配对/幂等要求。

**现有代码**

```c
DAPI_(void) SrpUninitialize();
```

**改进建议**

```c
DAPI_(void) SrpUninitialize(void);
```

#### 299. `tools/wix314/sdk/inc/srputil.h:37-40` · 中 / 文档

> 导出函数的返回语义缺少说明，导致调用方易误判：
> 1) `SrpCreateRestorePoint` 在权限不足（非管理员）、系统还原被组策略/注册表禁用、卷影复制服务不可用等常见情况下都会失败，头文件未说明返回失败是可忽略的（best-effort）还是致命错误，安装/卸载主流程很可能因 `FAILED(hr)` 而整体中止；
> 2) 未说明 `wzApplicationName` 的约束（空串、超长、含非法字符时的行为）以及 `SRP_ACTION_UNKNOWN` 传入时的语义（是拒绝返回 E_INVALIDARG 还是按默认动作处理）；
> 3) `SrpInitialize` 的 `fInitializeComSecurity` 何时必须为 TRUE、重复调用是否允许也没有说明。
> 建议补全上述注释，避免调用方在失败路径上做出错误决策。

**现有代码**

```c
DAPI_(HRESULT) SrpCreateRestorePoint(
    __in_z LPCWSTR wzApplicationName,
    __in SRP_ACTION action
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 300. `tools/wix314/sdk/inc/timeutil.h:10-11` · 中 / 文档

> 两个时间字符串接口的参数契约不清晰，调用方极易误用：
> 1) `wzTime` 仅标注 `__in_z`，但未说明支持的格式（是否必须为 ISO8601/RFC3339、是否允许毫秒、小数秒、时区后缀 `Z`/`+08:00`、是否依赖当前 Locale），也未说明 TimeFromString 与 TimeFromString3339 的区别（后者按 RFC3339 严格解析？前者宽松/本地时间？）。
> 2) `pFileTime` 仅标注 `__out`，未说明失败时（返回 E_INVALIDARG / E_FAIL 等）是否会把 `*pFileTime` 置为 0，若实现是“先解析后写入”，失败时输出为未初始化垃圾值，调用方在忽略 HRESULT 时会读到脏数据。
> 3) 未说明输入非法/为 NULL 时的返回值约定，也未说明 FILETIME 结果按 UTC 还是本地时间解释（FILETIME 无时区语义，若字符串带本地时间会引入 DST 边界错误）。
> 建议在头文件中补充简要注释，明确输入格式、时区语义与失败时的输出状态；实现中对 `wzTime == NULL || pFileTime == NULL` 做前置校验并返回 E_INVALIDARG，同时失败路径先 `*pFileTime = 0`。

**现有代码**

```c
    __in_z LPCWSTR wzTime,
    __out FILETIME* pFileTime
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 301. `tools/wix314/sdk/inc/timeutil.h:17-20` · 中 / 文档

> 三个返回字符串的接口（TimeCurrentTime / TimeCurrentDateTime / TimeSystemDateTime）使用 `__deref_out_z LPWSTR* ppwz` 分配新缓冲区，但头文件完全未声明所有权契约：
> 1) 内存由哪个分配器分配（StrAlloc / MemAlloc / CoTaskMemAlloc），调用方应使用 `StrFree`（见 strutil.h 的 `ReleaseStr` 宏）还是 `CoTaskMemFree` 释放？释放函数不匹配会直接导致堆损坏。
> 2) 失败时是否保证 `*ppwz == NULL`（即调用方能否无条件 `ReleaseStr(*ppwz)`），这决定了清理代码是否需要先判空。
> 3) `fGMT` 的语义未说明：TRUE 输出 UTC、FALSE 输出本地时间？对应格式串（如 `YYYY-MM-DDTHH:MM:SSZ`）也未说明，调用方难以做字符串比较/序列化。
> 建议在注释中明确分配器与释放函数、失败时输出置 NULL 的保证，以及 fGMT 对应的具体格式与时区含义。

**现有代码**

```c
HRESULT DAPI TimeCurrentTime(
    __deref_out_z LPWSTR* ppwz,
    __in BOOL fGMT
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 302. `tools/wix314/sdk/inc/timeutil.h:27` · 低 / 文档

> `pst` 的入参约束未声明：SYSTEMTIME 中 wDayOfWeek 会被忽略还是参与计算？wYear/wMonth/wDay/wHour/wMinute/wSecond/wMilliseconds 的取值范围和越界处理（返回 E_INVALIDARG 还是静默钳制）？当 `fGMT == FALSE` 且该 SYSTEMTIME 表示本地时间时，是否存在 DST 不存在/重复时刻（如 02:30 春季跳变）的处理约定？这些都会直接影响输出字符串的正确性，建议补充注释说明。另外指针书写风格 `const SYSTEMTIME *pst` 与本文件其它声明（`FILETIME* pFileTime`、`LPWSTR* ppwz`）不一致，建议统一为 `const SYSTEMTIME* pst`。

**现有代码**

```c
    __in const SYSTEMTIME *pst,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 303. `tools/wix314/sdk/inc/svcutil.h:10` · 中 / 缺陷

> `ReleaseServiceHandle` 宏存在三处隐患：1) 只用裸 `if` 而未用 `do { ... } while (0)` 包裹，调用方写成 `if (x) ReleaseServiceHandle(h); else ...` 时 `else` 会错误地绑定到宏内的 `if` 上（dangling else）；2) 参数 `h` 未加括号且被多次求值（判断一次、关闭一次、赋值一次），若传入带副作用的表达式（如 `arr[i++]`）会得到错误结果；3) 无条件忽略 `CloseServiceHandle` 的返回值并直接置 NULL，关闭失败时句柄会被覆盖、无法重试，造成句柄泄漏。建议改为 do/while(0) + 括号包裹，且仅在关闭成功（或句柄本身无效）时才置 NULL。

**现有代码**

```c
#define ReleaseServiceHandle(h) if (h) { ::CloseServiceHandle(h); h = NULL; }
```

**改进建议**

```c
#define ReleaseServiceHandle(h) do { if ((h)) { ::CloseServiceHandle(h); (h) = NULL; } } while (0)
```

#### 304. `tools/wix314/sdk/inc/svcutil.h:10` · 中 / 缺陷

> 该头文件通过 `extern "C"` 明确声明可被 C 代码包含，但宏体内部使用了 C++ 专属的作用域解析运算符 `::CloseServiceHandle`，一旦被 C 编译单元包含并展开将直接编译失败。C 语言下应直接使用 `CloseServiceHandle(h)`（宏在 C 中不需要全局作用域限定），可考虑按 `#ifdef __cplusplus` 区分。

**现有代码**

```c
#define ReleaseServiceHandle(h) if (h) { ::CloseServiceHandle(h); h = NULL; }
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 305. `tools/wix314/sdk/inc/svcutil.h:15` · 中 / 文档

> `SvcQueryConfig` 的契约不完整：输出参数 `ppConfig` 由 `QueryServiceConfigW` 内部用 LocalAlloc 分配，调用方必须用 `LocalFree` 释放，但头文件未做任何说明；同时未定义 `ppConfig` 为 NULL、`sch` 无效或查询失败（返回非 ERROR_SUCCESS 时 `*ppConfig` 是否被置空）时的行为，调用方极易遗漏释放导致内存泄漏，或在失败路径上误用未初始化指针。建议补充注释说明所有权与失败语义，并在实现中保证失败时 `*ppConfig = NULL`。

**现有代码**

```c
    __out QUERY_SERVICE_CONFIGW** ppConfig
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 306. `tools/wix314/sdk/inc/svcutil.h:14` · 低 / 可维护性

> 头文件直接使用了 `SC_HANDLE`、`QUERY_SERVICE_CONFIGW`、`HRESULT`、`DAPI` 等类型，却未包含 `<windows.h>` / `<winsvc.h>` 等定义这些类型的头文件，编译能否通过完全依赖调用方的 include 顺序，不利于可移植性与后续维护。建议在本头文件内显式包含所需系统头（或项目内的公共基础头）。

**现有代码**

```c
    __in SC_HANDLE sch,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 307. `tools/wix314/sdk/inc/userutil.h:10-11` · 中 / 缺陷

> `cchDest` 使用有符号 `int`，而项目内同类带缓冲区长度的接口（如 dirutil.h 的 `DirCreateTempPath`、logutil.h 的 `LogGetPath`）均使用 `DWORD`。SAL 的 `__out_ecount_z` 期望无符号计数，若调用方传入负数，实现中转换为 `size_t` 后会变成极大值，导致 SAL 静态检查失效并可能引发越界写；同时该接口没有在契约中说明缓冲区不足时的返回码（应为 `HRESULT_FROM_WIN32(ERROR_INSUFFICIENT_BUFFER)` 之类），建议统一为无符号计数并在注释中约定失败语义与成功时保证 NUL 结尾。

**现有代码**

```c
    __out_ecount_z(cchDest) LPWSTR wzDest,
    __in int cchDest,
```

**改进建议**

```c
    __out_ecount_z(cchDest) LPWSTR wzDest,
    __in DWORD cchDest,
```

#### 308. `tools/wix314/sdk/inc/userutil.h:27` · 中 / 文档

> `pbstrAdsPath` 作为 BSTR 输出参数，头文件未约定所有权与失败语义：调用方无法从声明得知成功时需 `SysFreeString` 释放、失败时是否被置为 NULL。若实现失败路径未初始化 `*pbstrAdsPath`，调用方按“成功即释放”的惯例处理会造成释放未初始化指针/野指针；反之若成功路径分配而调用方未释放则泄漏。建议补充注释并用 `__deref_out` 语义标注输出。

**现有代码**

```c
    __out BSTR *pbstrAdsPath
```

**改进建议**

```c
    // 成功时 *pbstrAdsPath 由调用方用 SysFreeString 释放；失败时保证置为 NULL。
    __deref_out BSTR *pbstrAdsPath
```

#### 309. `tools/wix314/sdk/inc/userutil.h:21` · 中 / 文档

> `lpfMember` 用 `__out LPBOOL` 标注，但头文件未说明“查询失败”与“不是成员”的区别（例如 RPC/网络错误时返回失败 HRESULT 且不写 `*lpfMember`）。建议在声明处明确：仅当返回 S_OK 时 `*lpfMember` 有效，调用方必须先判断 HRESULT 再使用该值，避免读取未初始化内存。

**现有代码**

```c
    __out LPBOOL lpfMember
```

**改进建议**

```c
    // 仅当返回 S_OK 时 *lpfMember 有效；失败时不修改该值，调用方不得据其判断成员身份。
    __out LPBOOL lpfMember
```

#### 310. `tools/wix314/sdk/inc/userutil.h:25-26` · 低 / 可维护性

> 同一文件内字符串指针命名风格不一致：`wzDest` / `wzObjectDomain` / `wzObjectName` 与 `pwzName` / `pwzDomain` 混用。WiX 中 `pwz` 一般用于由调用方分配/需释放的字符串，`wz` 用于普通宽字符串引用，混用会误导调用方对内存所有权的判断，建议统一命名。

**现有代码**

```c
    __in_z LPCWSTR wzObjectDomain, 
    __in_z LPCWSTR wzObjectName,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 311. `tools/wix314/sdk/inc/wcawow64.h:14-15` · 中 / 文档

> 这个头文件对外暴露的是有严格生命周期约束的接口，但声明处完全没有契约说明，调用方很容易误用：
> 1) `WcaDisableWow64FSRedirection` 与 `WcaRevertWow64FSRedirection` 是进程级状态修改，必须严格成对（且需要确认实现是否有引用计数/嵌套支持）；若 Disable 失败仍调用 Revert，或漏掉 Revert，会残留被重定向的 Wow64 文件系统视图，影响整个 MSI 进程后续所有文件访问。
> 2) `WcaInitializeWow64`/`WcaFinalizeWow64` 是否可重入、是否引用计数，决定了重复 Initialize 后一次 Finalize 会不会提前释放状态。
> 3) 进程级标志的读写是否线程安全，接口是否允许并发调用，也需要在声明处注明。
> 建议在此处补充注释，明确配对要求、可重入/引用计数语义、线程安全约定，以及失败后（例如 Disable 返回失败）调用方应如何处理与还原。

**现有代码**

```c
HRESULT WIXAPI WcaDisableWow64FSRedirection();
HRESULT WIXAPI WcaRevertWow64FSRedirection();
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 312. `tools/wix314/sdk/inc/wcawow64.h:11-12` · 低 / 可维护性

> C 语言中空参数列表 `()` 表示“参数未指定/未提供原型”，而不是“无参数”，会关闭编译器对实参个数与类型的检查；在启用 -Wstrict-prototypes 或 C 模式严格编译时还会产生告警，一旦调用方误传参数也不会被诊断出来。虽然 sdk/inc 下其他头文件（如 wcautil.h）沿用了 `()` 风格，仍建议新声明的无参接口写成 `(void)`，以便在 C 编译单元中获得完整的原型检查。同一问题也存在于 `WcaIsWow64Process`/`WcaIsWow64Initialized` 等其余无参声明上。

**现有代码**

```c
HRESULT WIXAPI WcaInitializeWow64();
BOOL WIXAPI WcaIsWow64Process();
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 313. `tools/wix314/sdk/inc/uriutil.h:67-72` · 中 / 可维护性

> `UriCanonicalize` 在本文件中被重复声明（第 35-37 行与第 70-72 行）。虽然 C/C++ 允许完全相同的重复声明，但后续只需修改其中一处（例如调整 SAL 注解或参数类型）就会导致两处契约不一致，且往往只有链接/调用方一侧暴露问题。建议删除第 70-72 行的重复声明，仅在文件前部保留一份。

**现有代码**

```c
    __in_z_opt LPWSTR wzQueryString
    );

HRESULT DAPI UriCanonicalize(
    __inout_z LPWSTR* psczUri
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 314. `tools/wix314/sdk/inc/uriutil.h:93-94` · 高 / 缺陷

> `pResolvedProtocol` 是输出参数，但被标注为指向 const 的指针（`__out_opt const URI_PROTOCOL*`）。SAL 与 const 语义互相矛盾：实现中对该参数赋值（`*pResolvedProtocol = ...`）会被编译器拒绝，只能靠强制转换绕过，从而可能掩盖真正的类型错误。同时 `ppwzResolvedUri` 用 `__out LPWSTR*` 也无法表达“返回新分配的字符串”，与同文件中 `UriFile`/`UriCrack` 使用的 `__deref_out_z` 不一致，调用方容易遗漏释放。建议改为 `__deref_out_z LPWSTR*` 与 `__out_opt URI_PROTOCOL*`。

**现有代码**

```c
    __out LPWSTR* ppwzResolvedUri,
    __out_opt const URI_PROTOCOL* pResolvedProtocol
```

**改进建议**

```c
    __deref_out_z LPWSTR* psczResolvedUri,
    __out_opt URI_PROTOCOL* pResolvedProtocol
```

#### 315. `tools/wix314/sdk/inc/uriutil.h:50-52` · 高 / 缺陷

> `UriCrackEx` 的职责是把 `wzUri` 拆解后**写入** `pUriInfo` 的各个 scz* 字段，但 `pUriInfo` 被标注为 `__in`，静态分析会认为该结构体只作为输入读取。更实际的风险是：头文件没有提供初始化函数，调用方通常传入栈上的未初始化 `URI_INFO`；一旦 `UriCrackEx` 中途失败，未赋值的字段仍是随机值，随后调用 `UriInfoUninitialize` 释放这些野指针会造成内存破坏。建议改为 `__out URI_INFO*`（实现需保证所有字段被初始化），并在注释中明确调用方必须零初始化以及失败后也需调用 `UriInfoUninitialize`。

**现有代码**

```c
HRESULT DAPI UriCrackEx(
    __in_z LPCWSTR wzUri,
    __in URI_INFO* pUriInfo
```

**改进建议**

```c
HRESULT DAPI UriCrackEx(
    __in_z LPCWSTR wzUri,
    __out URI_INFO* pUriInfo
```

#### 316. `tools/wix314/sdk/inc/uriutil.h:55-57` · 中 / 缺陷

> `UriInfoUninitialize` 会读取并释放 `URI_INFO` 中的 scz* 字段，通常还会把字段置空以支持重复调用；`__in` 无法表达这一“读取+修改”的语义，调用方和实现都可能误以为传入对象不会被改动。建议标注为 `__inout`，并在注释中说明其幂等性（可重复调用）以及必须与 `UriCrackEx` 配对使用。

**现有代码**

```c
void DAPI UriInfoUninitialize(
    __in URI_INFO* pUriInfo
    );
```

**改进建议**

```c
void DAPI UriInfoUninitialize(
    __inout URI_INFO* pUriInfo
    );
```

#### 317. `tools/wix314/sdk/inc/uriutil.h:84-86` · 中 / 可维护性

> `UriRoot` 返回的是新分配的根路径字符串（需要调用方 `ReleaseStr` 释放），但这里用 `__out LPWSTR*` 而非 `__deref_out_z`：既无法告诉静态分析工具“指针目标被分配”，也无法保证实现输出以 NUL 结尾，与同文件 `UriFile`、`UriCrack` 的约定不一致。参数名也与其它接口的 `scz` 前缀不统一。建议改为 `__deref_out_z LPWSTR* psczRoot`。

**现有代码**

```c
HRESULT DAPI UriRoot(
    __in_z LPCWSTR wzUri,
    __out LPWSTR* ppwzRoot,
```

**改进建议**

```c
HRESULT DAPI UriRoot(
    __in_z LPCWSTR wzUri,
    __deref_out_z LPWSTR* psczRoot,
```

#### 318. `tools/wix314/sdk/inc/uriutil.h:62-67` · 中 / 可维护性

> `UriCreate` 的 `wzHostName`/`wzUser`/`wzPassword`/`wzPath`/`wzQueryString` 仅作为输入被读取，却声明为可写的 `LPWSTR`，削弱了 const 正确性（调用方传入字符串字面量或 const 缓冲区会编译失败），也无法让编译器/SAL 校验实现不会篡改入参。建议统一改为 `LPCWSTR`。

**现有代码**

```c
    __in_z_opt LPWSTR wzHostName,
    __in INTERNET_PORT port,
    __in_z_opt LPWSTR wzUser,
    __in_z_opt LPWSTR wzPassword,
    __in_z_opt LPWSTR wzPath,
    __in_z_opt LPWSTR wzQueryString
```

**改进建议**

```c
    __in_z_opt LPCWSTR wzHostName,
    __in INTERNET_PORT port,
    __in_z_opt LPCWSTR wzUser,
    __in_z_opt LPCWSTR wzPassword,
    __in_z_opt LPCWSTR wzPath,
    __in_z_opt LPCWSTR wzQueryString
```

#### 319. `tools/wix314/sdk/inc/uriutil.h:59-60` · 低 / 可维护性

> `psczUri` 标注为 `__inout_z`，意味着调用时必须传入一个已分配且以 NUL 结尾的字符串指针；但该函数名为 `UriCreate`，语义上更像“生成一个新 URI”。若实现是重新分配输出，应使用 `__deref_opt_out_z LPWSTR*`；若确实是在已有字符串上追加/拼接，则应在头文件注释中写明“入参不能为未初始化指针，初始值可为空串”，避免调用方按分配语义传入未初始化变量导致读取野指针。

**现有代码**

```c
HRESULT DAPI UriCreate(
    __inout_z LPWSTR* psczUri,
```

**改进建议**

```c
HRESULT DAPI UriCreate(
    __deref_opt_out_z LPWSTR* psczUri,
```

#### 320. `tools/wix314/sdk/inc/wuautil.h:9-11` · 中 / 缺陷

> 这两个无参声明使用了空的参数列表 `()`。在 C 语义下 `()` 表示“参数未指定”（unprototyped），调用方即使误传参数编译器也不会报错，只有在 C++ 下才等价于无参。WiX SDK 的头文件同时被 C 和 C++ 使用（文件本身用 `__cplusplus` 分支包裹），建议显式写成 `(void)` 以获得参数个数检查，避免误调用导致的栈/ABI 错误。

**现有代码**

```c
HRESULT DAPI WuaPauseAutomaticUpdates();

HRESULT DAPI WuaResumeAutomaticUpdates();
```

**改进建议**

```c
HRESULT DAPI WuaPauseAutomaticUpdates(void);

HRESULT DAPI WuaResumeAutomaticUpdates(void);
```

#### 321. `tools/wix314/sdk/inc/wuautil.h:13-15` · 低 / 文档

> 接口契约缺少必要说明，容易误用：
> 1) `WuaPauseAutomaticUpdates` 与 `WuaResumeAutomaticUpdates` 修改的是机器级全局状态（停用/恢复 Windows Update 自动更新服务），必须在同一作用域内成对调用；若 Pause 成功后中途失败/异常返回而未调用 Resume，会使自动更新长期处于暂停状态。建议在注释中明确配对调用要求（RAII/成对调用）以及是否幂等。
> 2) `pfRestartRequired` 被标注为 `__out`（非 `_opt`），即调用方必须传入有效指针，NULL 行为未定义；建议补充说明由调用方保证非 NULL，并注明可能返回的错误码（如 WU 服务不可用、权限不足）以及“查询失败”与“无需重启”的区分方式（失败时 `*pfRestartRequired` 不应被使用）。

**现有代码**

```c
HRESULT DAPI WuaRestartRequired(
    __out BOOL* pfRestartRequired
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 322. `tools/wix314/sdk/inc/thmutil.h:9` · 高 / 缺陷

> ReleaseTheme 宏存在典型的宏缺陷：
> 1) 没有 do { ... } while (0) 包裹，在 `if (x) ReleaseTheme(p); else ...` 场景下展开会破坏 if/else 的悬挂分支；
> 2) 参数 p 未加括号且被求值两次（if 判断 + ThemeFree 调用），若传入 `arr[i++]` 之类的表达式会重复求值/越界；
> 3) 赋值未对 p 加括号。
> 建议改为 do/while(0) 形式，并约定只传简单左值。

**现有代码**

```c
#define ReleaseTheme(p) if (p) { ThemeFree(p); p = NULL; }
```

**改进建议**

```c
#define ReleaseTheme(p) do { if (p) { ThemeFree(p); (p) = NULL; } } while (0)
```

#### 323. `tools/wix314/sdk/inc/thmutil.h:74-75` · 高 / 缺陷

> 控件 ID / 页面 ID 的宽度不一致：此处 wId、wPageId 为 WORD，THEME_ASSIGN_CONTROL_ID.wId 与 THEME_PAGE.wId 同样是 WORD，而绝大多数公开 API（ThemeGetPage、ThemeShowPage、ThemeControlEnable、ThemeSetTextControl 等）使用 DWORD dwControl/dwPage。调用方传入 >0xFFFF 的 ID 时会被静默截断，导致查找失败或操作到错误的控件。建议统一为 DWORD（或在 ThemeLoadControls 解析赋值时显式做范围校验并返回错误）。

**现有代码**

```c
    WORD wId;
    WORD wPageId;
```

**改进建议**

```c
    DWORD dwId;
    DWORD dwPageId;
```

#### 324. `tools/wix314/sdk/inc/thmutil.h:309` · 高 / 缺陷

> ThemeDefWindowProc 缺少 DAPI_ 修饰。本文件其余所有导出函数均使用 DAPI_（定义见 dutil.h：`EXTERN_C type __stdcall`，并携带 dllimport/dllexport），这里只有 `LRESULT CALLBACK`，因此该符号不会从 dutil.dll 导出，SDK 使用方以隐式链接方式调用时会链接失败。建议与其他函数保持一致。

**现有代码**

```c
LRESULT CALLBACK ThemeDefWindowProc(
```

**改进建议**

```c
DAPI_(LRESULT) ThemeDefWindowProc(
```

#### 325. `tools/wix314/sdk/inc/thmutil.h:324` · 中 / 缺陷

> SAL 注解错误：rgdwPageIds 是输出数组（函数把查到的页面 ID 写入其中），却被标注为 `__in_ecount(cGetPages)`。这会让静态分析误判为必须由调用方预填，也会掩盖未初始化读取问题。应为 `__out_ecount(cGetPages)`。

**现有代码**

```c
    __in_ecount(cGetPages) DWORD* rgdwPageIds,
```

**改进建议**

```c
    __out_ecount(cGetPages) DWORD* rgdwPageIds,
```

#### 326. `tools/wix314/sdk/inc/thmutil.h:68` · 中 / 可维护性

> 在公共头文件中以 `const DWORD` 形式定义常量，在 C 编译单元中属于带外部链接的（暂定）定义：多个 .c/.cpp 同时包含该头文件时，C 链接阶段会出现 LNK2005 重复定义；在 C++ 中则是每个 TU 一份内部链接副本。该头文件本身声明为 C 兼容（extern "C"），建议改用 enum 常量或 #define，避免头文件内定义对象。

**现有代码**

```c
const DWORD THEME_FIRST_ASSIGN_CONTROL_ID = 1024; // Recommended first control id to be assigned.
```

**改进建议**

```c
enum { THEME_FIRST_ASSIGN_CONTROL_ID = 1024 }; // Recommended first control id to be assigned.
```

#### 327. `tools/wix314/sdk/inc/thmutil.h:477-478` · 中 / 缺陷

> const 语义不成立：ThemeStartBillboard/ThemeStopBillboard 必然要修改控件状态（当前图片索引、公告板定时器等，见 THEME_CONTROL 中 fBillboardLoops / wBillboardInterval 等可变字段）以及 hWnd 定时器，把它们声明为接收 `const THEME*` 会迫使实现里 const_cast 或绕过类型系统；调用方从只读对象传入也容易获得行为不一致。建议去掉 const，与 ThemeDrawBackground 等会修改内部状态（hwndHover 等）的接口保持一致。

**现有代码**

```c
DAPI_(HRESULT) ThemeStartBillboard(
    __in const THEME* pTheme,
```

**改进建议**

```c
DAPI_(HRESULT) ThemeStartBillboard(
    __in THEME* pTheme,
```

#### 328. `tools/wix314/sdk/inc/thmutil.h:531` · 中 / 文档

> 输出字符串的内存所有权与失败语义未定义：psczText 是库内部分配的 LPWSTR（通常需调用方用 MemFree 释放），还是指向控件内部缓冲区？函数失败时是否会将其置为 NULL？当前注释只写“gets the text of a control”。建议补充文档：成功时返回新分配、需 MemFree 的字符串（或明确为借用指针），失败/空控件时置 *psczText = NULL，避免调用方泄漏或误释放。

**现有代码**

```c
    __out LPWSTR* psczText
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 329. `tools/wix314/sdk/inc/thmutil.h:155` · 低 / 可维护性

> THEME 用 `HANDLE hIcon` 保存图标句柄，而文件中其他资源均使用强类型（HBITMAP/HFONT/HBRUSH/HIMAGELIST）。弱类型会让误传文件句柄/事件句柄等编译期不被发现，且 DestroyIcon 与 CloseHandle 混用风险增加。建议改为 HICON（THEME_BILLBOARD/THEME_CONTROL 的 hImage 也已用 HBITMAP）。

**现有代码**

```c
    HANDLE hIcon;
```

**改进建议**

```c
    HICON hIcon;
```

#### 330. `tools/wix314/sdk/inc/thmutil.h:253` · 中 / 可维护性

> 头文件不自洽：WIX_LOCALIZATION 定义在 locutil.h，本文件直接使用却未包含该头文件；同样 HBITMAP/HFONT/HBRUSH/PAINTSTRUCT/DRAWITEMSTRUCT 依赖 windows.h，DAPI_ 依赖 dutil.h。使用方若先包含 thmutil.h 会直接编译失败（报未知类型）。建议在文件顶部包含所需依赖（至少 `#include "locutil.h"`、`#include "dutil.h"`），或在注释中明确声明必须的包含顺序，便于 SDK 使用方正确集成。

**现有代码**

```c
    __in const WIX_LOCALIZATION *pLocStringSet
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 331. `tools/wix314/sdk/inc/thmutil.h:197` · 低 / 缺陷

> 该头文件同时供 C 与 C++ 使用，而 C 中 `ThemeUninitialize()` 表示参数未指定（可被任意实参调用且不报错），应写作 `(void)` 以表示无参数原型。建议改为 `DAPI_(void) ThemeUninitialize(void);`。

**现有代码**

```c
DAPI_(void) ThemeUninitialize();
```

**改进建议**

```c
DAPI_(void) ThemeUninitialize(void);
```

#### 332. `tools/wix314/sdk/inc/thmutil.h:180-181` · 低 / 文档

> THEME 中保存的 hwndParent/hwndHover 以及 THEME_CONTROL.hWnd 都是窗口句柄，公告板定时器、ThemeHandleKeyboardMessage、ThemeDefWindowProc、ThemeHoverControl 等接口会读写这些 UI 状态；但头文件未声明线程亲和性。跨线程（如工作线程更新进度/文本）调用会造成 SendMessage 死锁或句柄竞态。建议在文件头注释中明确：THEME 及所有 Theme* 接口必须在创建窗口的 UI 线程上调用（或说明内部是否做 PostMessage 编组）。

**现有代码**

```c
    HWND hwndParent; // parent for loaded controls
    HWND hwndHover; // current hwnd hovered over
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 333. `tools/wix314/sdk/inc/wcautil.h:17` · 中 / 缺陷

> `MessageExitOnLastError` / `MessageExitOnLastError1` 调用 `WcaErrorMessage` 时只传了 `MB_OK`，而同文件其它失败宏统一传 `INSTALLMESSAGE_ERROR | MB_OK`。这会导致“上一条错误”这条路径产生的消息不带错误图标/未被 MSI 当作错误消息展示（MSI 对消息类型的处理依赖 INSTALLMESSAGE_* 位），与同组宏行为不一致，排障时容易漏掉真实失败原因。建议统一为 `INSTALLMESSAGE_ERROR | MB_OK`。

**现有代码**

```c
#define MessageExitOnLastError(x, e, s)      { x = ::GetLastError(); x = HRESULT_FROM_WIN32(x); if (FAILED(x)) { ExitTrace(x, "%s", s); WcaErrorMessage(e, x, MB_OK, 0);  goto LExit; } }
```

**改进建议**

```c
#define MessageExitOnLastError(x, e, s)      { x = ::GetLastError(); x = HRESULT_FROM_WIN32(x); if (FAILED(x)) { ExitTrace(x, "%s", s); WcaErrorMessage(e, x, INSTALLMESSAGE_ERROR | MB_OK, 0);  goto LExit; } }
```

#### 334. `tools/wix314/sdk/inc/wcautil.h:23` · 中 / 缺陷

> 参数个数为 3 的分支调用的是 `ExitTrace2` 而不是 `ExitTrace3`，是明显的复制粘贴残留。虽然当前 `ExitTrace1/2/3` 都被定义为 `WcaLogError`（变参）所以能编译通过，但一旦将来把 `ExitTraceN` 按真实参数个数区分实现（或替换为带 `__format_string` 校验的包装），这里的第 3 个格式化参数 `u` 就会传错位置/触发格式串不匹配的未定义行为。建议改为 `ExitTrace3`。

**现有代码**

```c
#define MessageExitOnFailure3(x, e, f, s, t, u) if (FAILED(x)) { ExitTrace2(x, f, s, t, u); WcaErrorMessage(e, x, INSTALLMESSAGE_ERROR | MB_OK, 3, s, t, u);  goto LExit; }
```

**改进建议**

```c
#define MessageExitOnFailure3(x, e, f, s, t, u) if (FAILED(x)) { ExitTrace3(x, f, s, t, u); WcaErrorMessage(e, x, INSTALLMESSAGE_ERROR | MB_OK, 3, s, t, u);  goto LExit; }
```

#### 335. `tools/wix314/sdk/inc/wcautil.h:20` · 中 / 缺陷

> `MessageExitOnFailure*` 系列宏展开后是“裸 if + 语句块”，没有用 `do { ... } while (0)` 包裹。调用方写成 `if (cond) MessageExitOnFailure1(...); else ...;` 时会出现经典的 dangling-else 语义错乱（else 被绑定到宏内部 if，且宏尾部带 `;` 时会编译失败）；在无花括号的 if/for 中使用也可能只执行宏的一部分。建议所有带 `goto LExit` 的宏统一用 `do { ... } while (0)` 包裹（`MessageExitOnLastError*`、`MessageExitOnNullWithLastError*` 同理）。

**现有代码**

```c
#define MessageExitOnFailure(x, e, s)           if (FAILED(x)) { ExitTrace(x, "%s", s); WcaErrorMessage(e, x, INSTALLMESSAGE_ERROR | MB_OK, 0);  goto LExit; }
```

**改进建议**

```c
#define MessageExitOnFailure(x, e, s)           do { if (FAILED(x)) { ExitTrace(x, "%s", s); WcaErrorMessage(e, x, INSTALLMESSAGE_ERROR | MB_OK, 0);  goto LExit; } } while (0)
```

#### 336. `tools/wix314/sdk/inc/wcautil.h:103-104` · 中 / 缺陷

> `WcaLogError` 的 `szMessage` 实际是 printf 风格格式串（所有 `ExitTrace*` 宏都以它作为格式串传入可变参数），但没有标注 `__format_string`。缺少该 SAL 注解会让 `/analyze` 无法对调用点的参数个数/类型做校验，格式串与参数不匹配（如 `%s` 配 int）只能运行时崩溃。建议标注为 `__in_z __format_string LPCSTR szMessage`。

**现有代码**

```c
    __in HRESULT hr,
    __in LPCSTR szMessage,
```

**改进建议**

```c
    __in HRESULT hr,
    __in_z __format_string LPCSTR szMessage,
```

#### 337. `tools/wix314/sdk/inc/wcautil.h:274-276` · 中 / 缺陷

> `WcaWriteIntegerToCaData` 是向已有自定义操作数据“追加”内容（与 `WcaWriteStringToCaData`、`WcaWriteStreamToCaData` 同语义），会读取 `*ppwzCustomActionData` 现有缓冲并重新分配，因此注解应为 `__deref_inout_z_opt`。标成 `__deref_out_z_opt` 会让静态分析认为入参无需初始化，掩盖“调用方传入未初始化指针导致读取野指针”的问题，也与同组函数契约不一致。

**现有代码**

```c
HRESULT WIXAPI WcaWriteIntegerToCaData(
    __in int i, 
    __deref_out_z_opt LPWSTR* ppwzCustomActionData
```

**改进建议**

```c
HRESULT WIXAPI WcaWriteIntegerToCaData(
    __in int i, 
    __deref_inout_z_opt LPWSTR* ppwzCustomActionData
```

#### 338. `tools/wix314/sdk/inc/wcautil.h:167-169` · 中 / 可维护性

> 输出参数注解不一致：`WcaGetProperty`、`WcaGetIntProperty`、`WcaGetRecordString`、`WcaGetRecordFormattedString` 都标成 `__inout`，而语义相近的 `WcaGetFormattedProperty`、`WcaGetFormattedString`、`WcaGetTargetPath`、`WcaGetRecordFormattedInteger` 标成 `__out`。同一类“取属性/字段”接口出现两种契约，调用方无法从声明判断是否必须预先初始化（若实现内部对 `*ppwzData` 做 `StrAllocFree` 则实际是必填，否则是 `__out`）。建议统一为 `__out` 并在实现内部无需读取旧值；若确实需要传入已分配缓冲，请在声明旁注明契约。

**现有代码**

```c
HRESULT WIXAPI WcaGetProperty(
    __in_z LPCWSTR wzProperty,
    __inout LPWSTR* ppwzData
```

**改进建议**

```c
HRESULT WIXAPI WcaGetProperty(
    __in_z LPCWSTR wzProperty,
    __out LPWSTR* ppwzData
```

#### 339. `tools/wix314/sdk/inc/wcautil.h:257-258` · 低 / 缺陷

> `WcaReadStringFromCaData` / `WcaReadIntegerFromCaData` / `WcaReadStreamFromCaData` 的 `ppwzCustomActionData` 标注为 `__deref_in`，但这类“读取并从 CA 数据中前进指针”的接口必然回写 `*ppwzCustomActionData`（指向下一段数据），属于 in/out 语义。标注过严会导致静态分析误报（认为函数不应修改入参），也无法提示调用方必须传入有效指针。建议改为 `__deref_inout` 以便与 `WcaReadStreamFromCaData` 的输出语义一致。

**现有代码**

```c
HRESULT WIXAPI WcaReadStringFromCaData(
    __deref_in LPWSTR* ppwzCustomActionData,
```

**改进建议**

```c
HRESULT WIXAPI WcaReadStringFromCaData(
    __deref_inout LPWSTR* ppwzCustomActionData,
```

#### 340. `tools/wix314/sdk/inc/wcautil.h:351-353` · 低 / 安全

> `QuietExec`/`QuietExecEx` 会直接创建进程执行 `wzCommand`，但头文件没有对信任边界做任何说明。这类接口通常由 CA 从 MSI 属性（可能被用户/转换文件篡改，如 `CustomActionData`）拼出命令行；若调用方把不可信输入直接拼进命令行，存在命令注入风险（尤其带 `&&`、`|`、引号绕过等）。建议在声明处补充契约注释：`wzCommand` 必须由调用方校验/转义、不得包含未净化的属性值，并说明该缓冲会被原地修改（`__inout_z`）的原因（如追加 `QuietExec` 参数）。

**现有代码**

```c
HRESULT WIXAPI QuietExec(
    __inout_z LPWSTR wzCommand,
    __in DWORD dwTimeout
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 341. `tools/wix314/sdk/inc/wcautil.h:284-285` · 低 / 可维护性

> `WcaAddTempRecord` 通过 `cColumns` + 变参接收列值，头文件未约定每个变参必须为 `LPCWSTR`（或其它统一类型），也没有对 `cColumns` 与实参个数一致性的运行时/编译期约束：列数写少会读到未定义栈内容，类型不匹配会按指针解析导致崩溃；同时 `wzTable` 会拼进 SQL，若其来自不可信输入同样有 SQL 构造风险。建议在声明上方补充契约注释（“所有变参必须为 LPCWSTR，个数必须等于 cColumns；wzTable 必须为内部常量”），或提供接受 `LPCWSTR* rgpwzValues` 数组的重载以消除变参类型不安全问题。

**现有代码**

```c
HRESULT __cdecl WcaAddTempRecord(
    __inout MSIHANDLE* phTableView,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 342. `tools/wix314/sdk/inc/wcautil.h:25` · 低 / 可维护性

> 该头文件用 `extern "C"` 声明为 C 兼容接口（参数使用 `PCSTR`/`__in` 等），但头文件中的宏体使用了 C++ 作用域解析运算符 `::GetLastError()`。这使这些宏只能在 C++ 源文件中使用，纯 C 的 CA 一旦使用 `MessageExitOnLastError*` 系列就会编译失败。建议去掉 `::`（`GetLastError()` 在 C/C++ 中均可解析），使头文件真正满足其声明的 C 兼容性。

**现有代码**

```c
#define MessageExitOnNullWithLastError(p, x, e, s) if (NULL == p) { x = ::GetLastError(); x = HRESULT_FROM_WIN32(x); if (!FAILED(x)) { x = E_FAIL; } ExitTrace(x, "%s", s); WcaErrorMessage(e, x, MB_OK, 0);  goto LExit; }
```

**改进建议**

```c
#define MessageExitOnNullWithLastError(p, x, e, s) if (NULL == p) { x = GetLastError(); x = HRESULT_FROM_WIN32(x); if (!FAILED(x)) { x = E_FAIL; } ExitTrace(x, "%s", s); WcaErrorMessage(e, x, INSTALLMESSAGE_ERROR | MB_OK, 0);  goto LExit; }
```

#### 343. `tools/wix314/sdk/inc/wcautil.h:66` · 低 / 风格

> `WcaGlobalFinalize()` 使用空参数列表，在 C 中表示“参数未指定”而非“无参数”，会放过 `WcaGlobalFinalize(1)` 这类错误调用。建议写成 `WcaGlobalFinalize(void)`，与 C 兼容头文件的定位一致。

**现有代码**

```c
void WIXAPI WcaGlobalFinalize();
```

**改进建议**

```c
void WIXAPI WcaGlobalFinalize(void);
```

#### 344. `tools/wix314/sdk/inc/wcawrapquery.h:57` · 高 / 缺陷

> `1 << 31` 对 32 位有符号 int 属于未定义/实现定义行为（C++20 前为 UB，之后左移入符号位仍属未定义），在部分编译器/优化级别下 efmcColumn32 可能得到非预期值或触发 UBSan 报错；同时该枚举值与 DWORD 掩码按位或时会带入符号扩展，影响第 32 列的格式化判断。建议改用无符号字面量并显式转换。

**现有代码**

```c
    efmcColumn32 = 1 << 31,
```

**改进建议**

```c
    efmcColumn32 = (int)0x80000000u,
```

#### 345. `tools/wix314/sdk/inc/wcawrapquery.h:75` · 低 / 文档

> 注释中的参数名 `pfFormatMask` 与函数实际形参 `dwFormatMask` 不一致（该 API 是 DWORD 位掩码，不是指针），会误导调用方，建议同步为 dwFormatMask。

**现有代码**

```c
// Setting the pfFormatMask enables control over which fields will be formatted, and which will be left unchanged
```

**改进建议**

```c
// Setting the dwFormatMask enables control over which fields will be formatted, and which will be left unchanged
```

#### 346. `tools/wix314/sdk/inc/wcawrapquery.h:86` · 中 / 可维护性

> `0xFFFFFFFF` 作为“不追加列”的哨兵值是裸魔术数，出现在两个参数上，调用方容易误传 0（被当成第 0 列，虽然实现通常会当作无效列）而静默产生错误行为。建议在头文件里定义具名常量（如 WCA_WRAPQUERY_NO_COLUMN），并在注释中说明列索引越界（>= dwColumns）时的失败语义。同时，注释中说明会追加 ISInstalled/ISAction、SourcePath/TargetPath 四列，但头文件未导出这些追加列的索引常量，调用方只能硬编码 dwColumns / dwColumns+1，一旦追加顺序调整就会静默取错列。

**现有代码**

```c
    __in_opt DWORD dwComponentColumn,
```

**改进建议**

```c
    __in_opt DWORD dwComponentColumn,   // WCA_WRAPQUERY_NO_COLUMN(0xFFFFFFFF) 表示不追加；追加列索引建议以常量导出
```

#### 347. `tools/wix314/sdk/inc/wcawrapquery.h:128` · 中 / 可维护性

> `WcaFinishUnwrapQuery` 返回 void 且参数为 __in_opt，无法区分“句柄为 NULL”“部分初始化失败后的半成品句柄”“重复释放”等情况；一旦 WcaBeginUnwrapQuery 解析到一半失败、只分配了 pcdtColumnType/ppwzColumnNames/phRecords 中的一部分，调用方既无法知道清理是否成功，也无从判断释放是否完整。建议返回 HRESULT（保持与其它 API 一致）并明确“失败时也保证完成内部资源释放、句柄置空”的契约，或提供可对半初始化句柄做安全清理的说明。

**现有代码**

```c
void WIXAPI WcaFinishUnwrapQuery(
```

**改进建议**

```c
HRESULT WIXAPI WcaFinishUnwrapQuery(
```

#### 348. `tools/wix314/sdk/inc/wcawrapquery.h:95` · 中 / 可维护性

> 该接口隐含从自定义操作数据字符串中解析列数、行数并一次性分配/打开 dwRows 个 MSIHANDLE，但头文件未约定输入校验要求与失败语义：脏数据/超大数据（如 dwRows 被伪造为极大值）在没有上限校验时会导致内存耗尽或越界访问。建议在注释中明确必须校验的项（空指针、列数/行数上限、记录句柄打开失败时的回滚清理），并说明 *phWrapQuery 在失败时是否被置 NULL。

**现有代码**

```c
HRESULT WIXAPI WcaBeginUnwrapQuery(
```

**改进建议**

```c
HRESULT WIXAPI WcaBeginUnwrapQuery(
```

#### 349. `tools/wix314/sdk/inc/wiutil.h:193` · 严重 / 缺陷

> 函数指针签名与真实 MSI API 不一致：`MsiSetExternalUIRecord` 的第四个参数是「指向 PINSTALLUI_HANDLER_RECORD 的指针」（即 `PINSTALLUI_HANDLER_RECORD*`），这里少了一级指针。目前声明会让该 typedef 的调用方传入 `PINSTALLUI_HANDLER_RECORD`（本身就是函数指针）而被当作 out 参数写入，导致编译告警/错误，或在 x64 下因 ABI 不匹配（参数槽位大小不同）写坏栈上数据。同时该签名被 `WiuFunctionOverride` 的 `pfnMsiSetExternalUIRecord` 直接复用，错误会被传递到所有覆盖点。

**现有代码**

```c
    __out_opt PINSTALLUI_HANDLER_RECORD ppuiPrevHandler
```

**改进建议**

```c
    __out_opt PINSTALLUI_HANDLER_RECORD* ppuiPrevHandler
```

#### 350. `tools/wix314/sdk/inc/wiutil.h:22-23` · 中 / 缺陷

> 这两个释放宏存在三个隐患：1) 未用 `do { ... } while(0)` 包裹，在 `if (x) ReleaseMsi(h); else ...` 中会产生悬空 else（宏展开成两条语句，else 会绑定到宏内部 if 上）；2) 参数 `h` 被多次求值，传入 `p->h`/`*pp` 之类带副作用或含函数调用的表达式时会重复求值甚至释放错误句柄；3) 宏体使用 `::MsiCloseHandle`，使该宏只能在 C++ 中使用，而本头文件用 `extern "C"` 面向 C 调用者。建议改为 do/while 并给参数加括号，同时去掉 `::`。

**现有代码**

```c
#define ReleaseMsi(h) if (h) { ::MsiCloseHandle(h); }
#define ReleaseNullMsi(h) if (h) { ::MsiCloseHandle(h); h = NULL; }
```

**改进建议**

```c
#define ReleaseMsi(h) do { if (h) { MsiCloseHandle(h); } } while (0)
#define ReleaseNullMsi(h) do { if (h) { MsiCloseHandle(h); (h) = NULL; } } while (0)
```

#### 351. `tools/wix314/sdk/inc/wiutil.h:100` · 中 / 缺陷

> 进度栈使用硬编码的 64 个槽位且无任何容量常量/契约说明：`WiuInitializeExternalUI` 入栈与回调中按 `dwCurrentProgressIndex` 写入时若发生嵌套安装（MsiInstallProduct 内部再触发安装）或递归/并发调用，索引会越界写坏紧随其后的 `previousInstallUILevel`、`hwndPreviousParentWindow`、回调指针等字段，进而破坏外部 UI 的恢复逻辑。建议提取具名常量（如 `WIU_MSI_PROGRESS_MAX`），并在头文件中明确「单线程、最大嵌套深度 N，溢出时的行为（失败返回还是丢弃）」，同时让 `pExecuteContext` 标注为 `__out`/`__inout`。

**现有代码**

```c
    WIU_MSI_PROGRESS rgMsiProgress[64];
```

**改进建议**

```c
#define WIU_MSI_PROGRESS_MAX 64 // 外部 UI 进度栈最大嵌套深度，超出必须明确失败而非越界写入

    WIU_MSI_PROGRESS rgMsiProgress[WIU_MSI_PROGRESS_MAX];
```

#### 352. `tools/wix314/sdk/inc/wiutil.h:266-270` · 中 / 文档

> 所有返回 `LPWSTR*`/`LPWSTR**` 的封装（WiuGetProductInfo、WiuGetProductInfoEx、WiuGetProductProperty、WiuGetPatchInfoEx、WiuGetComponentPath、WiuLocateComponent、WiuEnumRelatedProductCodes 等）都没有注明输出参数的所有权与失败语义：调用方无法得知返回值必须用 `MemFree` 释放、失败时 `*psczValue` 是否被置空/是否部分写入、成功时是否可能为 NULL。以本仓库风格而言，这极易造成泄漏或对空指针解引用。建议在函数声明处统一注明：「失败时 *psczValue 恒为 NULL；成功时为 CoTaskMem/MemFree 分配的字符串，调用方负责释放」。

**现有代码**

```c
HRESULT DAPI WiuGetProductInfo(
    __in_z LPCWSTR wzProductCode,
    __in_z LPCWSTR wzProperty,
    __out LPWSTR* psczValue
    );
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 353. `tools/wix314/sdk/inc/wiutil.h:248` · 低 / 可维护性

> `WiuFunctionOverride` 只覆盖了部分已声明的函数指针类型：`PFN_MSIGETPATCHINFOEXW`、`PFN_MSIDETERMINEPATCHSEQUENCEW`、`PFN_MSIDETERMINEAPPLICABLEPATCHESW`、`PFN_MSIREMOVEPATCHESW`、`PFN_MSIENUMPRODUCTSW`、`PFN_MSIENUMPRODUCTSEXW` 对应的封装无法被注入替身，导致这些接口只能依赖真实 MSI 才能测试，与可替换指针的设计意图不一致。建议补齐这些覆盖参数，或在注释中说明为何刻意不提供覆盖。

**现有代码**

```c
    __in_opt PFN_MSISOURCELISTADDSOURCEEXW pfnMsiSourceListAddSourceExW
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 354. `tools/wix314/sdk/inc/wiutil.h:352` · 低 / 风格

> 参数名拼写错误（`Packag` 应为 `Package`），与 `PFN_MSIINSTALLPRODUCTW` 中的 `szPackagePath` 也不一致，容易在调用点造成混淆；建议修正为 `wzPackagePath`。

**现有代码**

```c
    __in_z LPCWSTR wzPackagPath,
```

**改进建议**

```c
    __in_z LPCWSTR wzPackagePath,
```

#### 355. `tools/wix314/sdk/inc/wiutil.h:1-2` · 低 / 可维护性

> 该头文件未包含任何依赖声明，却直接使用 `LPCWSTR`/`WINAPI`/`HWND`/`MSIHANDLE`、`INSTALLMESSAGE`、`INSTALLLOGMODE_*`、`INSTALLUILEVEL`、`INSTALLSTATE`、`INSTALLTYPE`、`MSIINSTALLCONTEXT`、`PMSIPATCHSEQUENCEINFOW`、`MAX_GUID_CHARS`、`DAPI` 以及 `__in`/`__deref_out_ecount_opt` 等 SAL 宏。若包含顺序不当（例如未先包含 windows.h/msi.h 与 DAPI 定义所在的 dutil.h），会直接编译失败，且 `INSTALLLOGMODE_*` 在 msi.h 缺省时宏定义被静默展开失败。建议显式 `#include <windows.h>`、`<msi.h>` 及 DAPI 头，或在文件顶部注释明确前置包含要求。

**现有代码**

```c
#pragma once
// Copyright (c) .NET Foundation and contributors. All rights reserved. Licensed under the Microsoft Reciprocal License. See LICENSE.TXT file in the project root for full license information.
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 356. `tools/wix314/sdk/inc/xmlutil.h:20` · 高 / 安全

> 加载类 API（XmlLoadDocument / XmlLoadDocumentEx / XmlLoadDocumentFromFile / XmlLoadDocumentFromFileEx / XmlLoadDocumentFromBuffer）只提供了 XML_LOAD_PRESERVE_WHITESPACE 一个属性，没有任何关闭 DTD/外部实体解析的开关。MSXML 默认会解析 DTD 并加载外部实体，因此加载不可信 XML（例如用户提供的配置文件）时可被构造 XXE：读取本地文件、发起 SSRF 请求，甚至在 msxml 旧版本上遍历网络资源；同时 XXE 也可用于 billion-laughs 式 DoS。建议新增安全默认值/开关（例如内部强制 setProperty("ProhibitDTD", TRUE)、resolveExternals=FALSE、validateOnParse=FALSE），并把这些能力暴露为显式 flags，默认走安全路径。

**现有代码**

```c
    XML_LOAD_PRESERVE_WHITESPACE = 1,
```

**改进建议**

```c
    XML_LOAD_PRESERVE_WHITESPACE = 1,
    XML_LOAD_DISABLE_DTD = 2,
    XML_LOAD_NO_EXTERNAL_RESOLUTION = 4,
```

#### 357. `tools/wix314/sdk/inc/xmlutil.h:39` · 中 / 缺陷

> 该头文件用 #ifdef __cplusplus 提供 extern "C" 兼容包装，说明它可能被 C 编译器包含；但这里在公开声明中使用了 C++ 默认实参 `= NULL`，一旦被 C 源文件包含会直接编译错误（而且这是本目录中唯一在 C 接口上使用默认实参的头文件，与其它 SDK 头文件风格不一致）。建议把默认实参限定在 C++ 分支内。

**现有代码**

```c
    __out_opt IXMLDOMElement** ppixeRootElement = NULL
```

**改进建议**

```c
#ifdef __cplusplus
    __out_opt IXMLDOMElement** ppixeRootElement = NULL
#else
    __out_opt IXMLDOMElement** ppixeRootElement
#endif
```

#### 358. `tools/wix314/sdk/inc/xmlutil.h:157` · 中 / 缺陷

> wzPath 类型为 LPCWSTR（const wchar_t*），却标注为 __inout，语义自相矛盾：既暗示调用方会写回该缓冲区，又未标注 __in_z 保证空终止，会误导 PREfast/SAL 静态分析并掩盖真实契约。这里只读取路径字符串，应改为 __in_z。

**现有代码**

```c
    __inout LPCWSTR wzPath
```

**改进建议**

```c
    __in_z LPCWSTR wzPath
```

#### 359. `tools/wix314/sdk/inc/xmlutil.h:28-29` · 中 / 可维护性

> XmlInitialize/XmlUninitialize 是成对的进程级全局初始化，但接口未暴露引用计数或句柄，文档也未说明其调用契约。多模块或多次初始化后，任一模块调用 XmlUninitialize 都会把全局资源（COM 初始化、schema cache 等）提前释放，后续 XmlLoadDocument* 等 API 将出现竞态或崩溃；重复调用 XmlUninitialize 也可能导致引用计数下溢。建议内部用引用计数 + 临界区保护（Initialize/Uninitialize 成对计数），或至少在头文件中明确要求“进程生命周期内只初始化/反初始化一次，且必须单线程调用”。

**现有代码**

```c
HRESULT DAPI XmlInitialize();
void DAPI XmlUninitialize();
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 360. `tools/wix314/sdk/inc/xmlutil.h:45-47` · 低 / 可维护性

> dwAttributes 被声明为裸 DWORD，而不是 XML_LOAD_ATTRIBUTE，调用方可以随意传入未知位，实现侧（以及静态分析）无法校验取值；同时 XML_LOAD_ATTRIBUTE 作为位标志枚举既没有定义成 DWORD 的 typedef，也没有任何 ">> " 命名约定说明。建议把 XML_LOAD_ATTRIBUTE 定义为 DWORD 的标志类型，并让参数使用该类型（两个 Ex 接口都需改）。

**现有代码**

```c
HRESULT DAPI XmlLoadDocumentEx(
    __in_z LPCWSTR wzDocument,
    __in DWORD dwAttributes,
```

**改进建议**

```c
HRESULT DAPI XmlLoadDocumentEx(
    __in_z LPCWSTR wzDocument,
    __in XML_LOAD_ATTRIBUTE dwAttributes,
```

#### 361. `tools/wix314/sdk/inc/xmlutil.h:91` · 中 / 文档

> 输出内存的所有权没有说明。同一头文件里 XmlGetText/XmlGetAttribute/XmlNextAttribute/XmlNextElement 返回 BSTR（须 SysFreeString），而 XmlGetAttributeEx 返回 LPWSTR（按本项目约定应由 StrAlloc 分配、StrFree 释放），XmlSaveDocumentToBuffer 返回 BYTE*（MemAlloc/MemFree）。调用方极易用错释放函数（例如对 StrAlloc 出来的 LPWSTR 调 SysFreeString），跨 CRT 分配/释放还会造成堆破坏。建议在注释中明确每个输出参数的分配器与释放函数（BSTR → SysFreeString，LPWSTR → StrFree，BYTE* → MemFree）。

**现有代码**

```c
    __deref_out_z LPWSTR* psczAttributeValue
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 362. `tools/wix314/sdk/inc/xmlutil.h:161-162` · 低 / 缺陷

> ppbDest 的 bcount 依赖 pcbDest，但 pcbDest 被标注为 __out（入口时未初始化），SAL 在入口/返回值校验时可能基于未初始化值做判断（正确写法通常配合 __deref_out_bcount_full 或明确标注为输出长度）；此外返回的 BYTE* 由谁分配、谁来释放完全没有契约说明，调用方容易泄漏或因用错释放函数而崩溃。建议改为 __deref_out_bcount_full(*pcbDest) 并注明释放方式（如 MemFree）。

**现有代码**

```c
    __deref_out_bcount(*pcbDest) BYTE** ppbDest,
    __out DWORD* pcbDest
```

**改进建议**

```c
    __deref_out_bcount_full(*pcbDest) BYTE** ppbDest,
    __out DWORD* pcbDest
```

#### 363. `tools/wix314/sdk/inc/strutil.h:9` · 中 / 缺陷

> 这些 `Release*` 宏都是未经 `do { ... } while (0)` 包裹的多语句宏：
> 1) 在 `if (cond) ReleaseStr(p); else ...` 场景会产生悬挂 else 或直接编译错误（`ReleaseStrArray`/`ReleaseNullStrArray` 带花括号后再跟分号同样如此）；
> 2) `ReleaseStr(pwz)` 中 `pwz` 被求值两次，若传入带副作用的表达式（如 `ReleaseStr(GetPtr())`、`ReleaseStr(p++)`）会重复执行；
> 3) `ReleaseStr`/`ReleaseStrArray` 释放后不置空，与 `ReleaseNullStr` 语义不一致，容易二次释放。建议统一用 `do { ... } while (0)` 包裹，并尽量用内联函数或临时变量避免重复求值。

**现有代码**

```c
#define ReleaseStr(pwz) if (pwz) { StrFree(pwz); }
```

**改进建议**

```c
#define ReleaseStr(pwz) do { if (pwz) { StrFree(pwz); } } while (0)
```

#### 364. `tools/wix314/sdk/inc/strutil.h:15` · 中 / 安全

> `StrSecureZeroFreeString` 返回 HRESULT，这里直接丢弃并把指针置 NULL：清零失败时敏感数据可能残留在已释放的堆内存中，调用方完全无法感知。另外 `StrSecureZeroString`/`StrSecureZeroFreeString` 没有长度参数，只能按 `wcslen` 擦除到首个 NUL，若缓冲区在 NUL 之后还存有敏感内容（如密码拼接残留）不会被清零。建议至少检查/保留返回值，并提供带 `cch` 的擦除接口以覆盖整个分配块。

**现有代码**

```c
#define ReleaseNullStrSecure(pwz) if (pwz) { StrSecureZeroFreeString(pwz); pwz = NULL; }
```

**改进建议**

```c
#define ReleaseNullStrSecure(pwz) do { if (pwz) { (void)StrSecureZeroFreeString(pwz); pwz = NULL; } } while (0)
```

#### 365. `tools/wix314/sdk/inc/strutil.h:11` · 中 / 缺陷

> 宏体中的 `::SysFreeString` 是 C++ 专有语法，而本头文件用 `extern "C"` 声明并面向 C 调用方；C 编译器展开 `ReleaseBSTR`/`ReleaseNullBSTR` 时会直接报错。建议去掉全局作用域限定写成 `SysFreeString(bstr)`。

**现有代码**

```c
#define ReleaseBSTR(bstr) if (bstr) { ::SysFreeString(bstr); }
```

**改进建议**

```c
#define ReleaseBSTR(bstr) do { if (bstr) { SysFreeString(bstr); } } while (0)
```

#### 366. `tools/wix314/sdk/inc/strutil.h:17` · 中 / 缺陷

> `DeclareConstBSTR` 把字节长度塞进单个 `WCHAR`，`sizeof(wz)-sizeof(WCHAR)` 超过 65535 时会被静默截断，生成的 BSTR 长度字段错误；而且 `sizeof(wz)` 只对数组字面量成立，若传入指针会得到指针大小并生成非法 BSTR。`UseConstBSTR` 再用 `const_cast` 去掉 const 后交给 BSTR API，一旦被写入或传给 `SysFreeString`（例如误用 `ReleaseBSTR`）就会写只读段或破坏堆。建议对长度做编译期检查（`static_assert`/数组长度约束），并明确该 BSTR 只读、禁止释放；或改用运行时分配的 BSTR。

**现有代码**

```c
#define DeclareConstBSTR(bstr_const, wz) const WCHAR bstr_const[] = { 0x00, 0x00, sizeof(wz)-sizeof(WCHAR), 0x00, wz }
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 367. `tools/wix314/sdk/inc/strutil.h:28` · 中 / 缺陷

> `StrTrimCapacity` 需要读取并重分配调用方已有的 `*ppwz`，语义是 in/out，却标注为 `__deref_out_z`（纯输出）。静态分析和调用方按 out 语义传未初始化指针时会触发未初始化读取/崩溃，也会漏报真实问题。建议改为 `__deref_inout_z`。

**现有代码**

```c
HRESULT DAPI StrTrimCapacity(
```

**改进建议**

```c
HRESULT DAPI StrTrimCapacity(
    __deref_inout_z LPWSTR* ppwz
    );
```

#### 368. `tools/wix314/sdk/inc/strutil.h:73` · 中 / 缺陷

> `StrAllocPrefix` 是“在已有字符串前插入前缀”，必然读取/重分配 `*ppwz`；同族的 `StrAllocConcat`、`StrAllocConcatSecure`、`StrAnsiAllocConcat`、`StrAllocConcatFormatted` 也是追加到已有缓冲区。它们标 `__deref_out_z` 与实际契约不符，建议统一为 `__deref_inout_z`（ANSI 版本为 `__deref_inout_z LPSTR*`），否则调用方按输出语义传未初始化指针会导致崩溃，SAL 也无法发现该问题。

**现有代码**

```c
HRESULT DAPI StrAllocPrefix(
```

**改进建议**

```c
HRESULT DAPI StrAllocPrefix(
    __deref_inout_z LPWSTR* ppwz,
    __in_z LPCWSTR wzPrefix,
    __in DWORD_PTR cchPrefix
    );
```

#### 369. `tools/wix314/sdk/inc/strutil.h:194` · 中 / 缺陷

> `pcch` 是 `__out` 输出参数，这里却把它作为 `pwzMultiSz` 的 `__in_ecount(*pcch)` 输入长度。调用前 `*pcch` 未初始化，SAL 会按其值推断缓冲区大小，可能误报或掩盖真实越界。MultiSz 本身以双 NUL 结尾，不需要额外长度；建议去掉 `_ecount`，改为 `__in __nullnullterminated LPCWSTR pwzMultiSz`。

**现有代码**

```c
HRESULT DAPI MultiSzLen(
```

**改进建议**

```c
HRESULT DAPI MultiSzLen(
    __in __nullnullterminated LPCWSTR pwzMultiSz,
    __out DWORD_PTR* pcch
    );
```

#### 370. `tools/wix314/sdk/inc/strutil.h:198` · 中 / 缺陷

> `pcchMultiSz` 声明为 `__inout_opt`（允许为 NULL），但 `ppwzMultiSz` 的 `__deref_inout_ecount(*pcchMultiSz)` 会解引用该计数。两者契约矛盾：传入 NULL 时注解引用了空指针，且实际缓冲区长度未知，越界风险无法被分析发现。建议去掉 `_ecount`，或把计数参数改为必填 `__inout DWORD_PTR*`。同样问题也存在于下方 `MultiSzInsertString`。

**现有代码**

```c
HRESULT DAPI MultiSzPrepend(
```

**改进建议**

```c
HRESULT DAPI MultiSzPrepend(
    __deref_inout __nullnullterminated LPWSTR* ppwzMultiSz,
    __inout_opt DWORD_PTR *pcchMultiSz,
    __in __nullnullterminated LPCWSTR pwzInsert
    );
```

#### 371. `tools/wix314/sdk/inc/strutil.h:177` · 中 / 缺陷

> `ppbDest` 是 `BYTE**`，用 `__out_bcount(*pcbDest)` 会把“指针本身”当成输出缓冲区，应该用 `__deref_out_bcount`；同时长度参数是 `__out_opt`，若调用方传 NULL，`_bcount(*pcbDest)` 会在注解中解引用空指针，契约自相矛盾。此外长度类型使用 `DWORD`，与同文件 `StrAllocBase85Decode` 的 `DWORD_PTR` 不一致，64 位下有截断风险。建议改为 `__deref_out_bcount(*pcbDest) BYTE**` + `__out DWORD_PTR*`（或明确允许 NULL 时改用不带 bcount 的注解），并与 Base85 版本统一长度类型。

**现有代码**

```c
HRESULT DAPI StrAllocHexDecode(
```

**改进建议**

```c
HRESULT DAPI StrAllocHexDecode(
    __in_z LPCWSTR wzSource,
    __deref_out_bcount(*pcbDest) BYTE** ppbDest,
    __out DWORD_PTR* pcbDest
    );
```

#### 372. `scripts/verify_msi.ps1:3` · 高 / 缺陷

> 两个脚本都把 `$ErrorActionPreference` 固定为 `Continue`，且 msiexec 的退出码只写日志、不做任何判定：MSI 缺失(1619)、安装失败(1603)、被策略阻止(1625)、需要重启(3010)等情况都会被当作“流程跑完”的通过结果，自动化使用时无法感知失败。此外 verify_msi.ps1 声明“需要管理员权限运行”却从未校验是否已提权。建议先显式做提权校验；对每条 msiexec 结果做白名单校验(仅 0/3010 视为成功)，关键步骤失败时记录 FAIL 并以非 0 退出码结束(如 `exit 1`)，同时在结尾输出显式的 PASS/FAIL 汇总。

**现有代码**

```powershell
$ErrorActionPreference = "Continue"
```

**改进建议**

```powershell
#Requires -RunAsAdministrator
$ErrorActionPreference = "Continue"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "本脚本需要以管理员权限运行"
}
```

#### 373. `scripts/verify_msi.ps1:4` · 中 / 安全

> 硬编码开发者本机绝对路径：换用户、换机器或仓库不在该位置时，`$logDir` 下的 MSI 不存在、`Set-Content $out` 也会失败，脚本却继续执行。更值得注意的是，这里会以提升权限的 msiexec 安装位于用户可写目录（`C:\Users\<user>\...`）中的 MSI，安装前未做任何来源/完整性校验，普通用户替换该文件即可获得管理员级别的代码执行。建议用 `$PSScriptRoot` 派生路径，并在安装前 `Test-Path` + 校验签名或哈希。

**现有代码**

```powershell
$root   = "C:\Users\Liyian\WorkBuddy\python-pkg\pyenv-inspector"
```

**改进建议**

```powershell
$root   = Split-Path -Parent $PSScriptRoot
```

#### 374. `scripts/verify_msi.ps1:7-8` · 高 / 缺陷

> 两个 MSI 路径在调用 `Start-Process msiexec` 前没有存在性检查。文件缺失时 Start-Process 只产生非终止错误、`$p` 为 `$null`，于是 `INSTALL_100_EXIT=` 会写成空值，后面的 EXE/LNK/ARP 检查全部基于“未安装”状态得出结论，日志使用者很难看出这是脚本前置条件错误。建议启动前逐个校验。

**现有代码**

```powershell
$msi100 = "$logDir\PyEnvInspector-1.0.0.msi"
$msi101 = "$logDir\PyEnvInspector-1.0.1.msi"
```

**改进建议**

```powershell
foreach ($msi in @($msi100, $msi101)) {
    if (-not (Test-Path -LiteralPath $msi)) { throw "未找到 MSI: $msi" }
}
```

#### 375. `scripts/verify_msi.ps1:13-17` · 中 / 缺陷

> `Get-ARP` 仅按 DisplayName 相等过滤后 `Select-Object -First 1`，会掩盖“同一 DisplayName 存在多条卸载注册项”的情况(MajorUpgrade 未清理旧产品导致新旧版本并存、机器级同名安装、残留或伪造项)，返回哪一条取决于枚举顺序，使升级/卸载判定失真；更严重的是会用这个可能错误的 `PSChildName` 去执行 `msiexec /x`，卸载掉不属于本次测试的产品。另外 verify_msi.ps1 只查了 64 位注册表视图，32 位包注册在 Wow6432Node 下会查不到。建议返回全部匹配项，限定作用域(perUser 只查 HKCU，或用 InstallLocation/SystemComponent/WindowsInstaller 交叉校验)，并在调用处断言匹配数量为 1、版本符合预期，匹配到多条时显式报告歧义而不是取第一条。

**现有代码**

```powershell
function Get-ARP {
    Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*" -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -eq $name } |
        Select-Object -First 1 DisplayName, DisplayVersion, PSChildName
}
```

**改进建议**

```powershell
function Get-ARP {
    Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*" -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -eq $name } |
        Select-Object DisplayName, DisplayVersion, PSChildName
}
```

#### 376. `scripts/verify_msi.ps1:22-23` · 高 / 缺陷

> msiexec 的退出码只记录、不参与流程控制：安装失败(1603 致命错误、1638 已存在其他版本、1625 被策略阻止)或升级被拒(1619/1638/1603)后仍继续做文件/快捷方式/ARP 检查并进入下一阶段，日志里出现大量 FAIL 也无法定位根因，甚至会把升级失败后的旧版本 1.0.0 当成“升级成功”。建议封装 msiexec 调用，仅 0/3010 视为成功，非 0 即记录并中止(或至少标记整体失败)；同时显式传 `/norestart`/`REBOOT=ReallySuppress` 抑制重启，并在升级后断言 `ARP_VERSION_AFTER_UPGRADE` 等于 1.0.1。

**现有代码**

```powershell
$p = Start-Process msiexec -ArgumentList "/i", "`"$msi100`"", "/qn", "/l*v", "`"$logDir\v100.log`"" -Wait -PassThru
Add-Content $out "INSTALL_100_EXIT=$($p.ExitCode)"
```

**改进建议**

```powershell
function Invoke-Msi([string[]]$Arguments, [string]$Step) {
    $p = Start-Process msiexec -ArgumentList ($Arguments + @('/norestart', 'REBOOT=ReallySuppress')) -Wait -PassThru
    Add-Content $out "$Step`_EXIT=$($p.ExitCode)"
    if ($p.ExitCode -notin 0, 3010) { throw "$Step 失败，msiexec 退出码 $($p.ExitCode)" }
    return $p
}
$null = Invoke-Msi @('/i', "`"$msi100`"", '/qn', '/l*v', "`"$logDir\v100.log`"") 'INSTALL_100'
```

#### 377. `scripts/verify_msi.ps1:36-40` · 高 / 缺陷

> 冒烟测试按进程名 `PyEnvInspector` 匹配并 `Stop-Process -Name ... -Force`：机器上已存在用户自己运行的实例时会把“启动失败”判成 APP_RUNNING=True，随后还会强杀用户正在使用的所有同名进程，超出本次启动范围；固定 6 秒等待也无法区分“启动即崩溃”和“启动较慢”。建议用 `Start-Process $exe -PassThru` 拿到本次启动的进程对象，按其 Id 轮询等待主窗口/存活状态并设置超时(例如 30 秒)，结束时只 `Stop-Process -Id $proc.Id -Force`(或用 `taskkill /PID ... /T` 清理子进程，放在 finally 中)。

**现有代码**

```powershell
    Start-Process $exe
    Start-Sleep -Seconds 6
    $proc = Get-Process PyEnvInspector -ErrorAction SilentlyContinue
    Add-Content $out ("APP_RUNNING=" + ($null -ne $proc))
    if ($proc) { Stop-Process -Name PyEnvInspector -Force }
```

**改进建议**

```powershell
    $app = Start-Process $exe -PassThru
    try {
        Start-Sleep -Seconds 6
        Add-Content $out ("APP_RUNNING=" + (-not $app.HasExited))
    } finally {
        if ($app -and -not $app.HasExited) { Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Seconds 1
    }
```

#### 378. `scripts/verify_msi.ps1:47-49` · 中 / 测试

> 升级步骤只输出 ARP 版本和 EXE 是否存在，既不与期望值 1.0.1 比较（`$arp2` 为 $null 时只会写出空字符串），也不重跑启动冒烟、快捷方式/文件数检查。升级后的二进制若因依赖缺失无法启动，验证日志依旧看起来“通过”。建议断言版本等于 1.0.1 并对升级后的安装重复一次冒烟与快捷方式检查。

**现有代码**

```powershell
$arp2 = Get-ARP
Add-Content $out ("ARP_VERSION_AFTER_UPGRADE=" + $arp2.DisplayVersion)
Add-Content $out ("EXE_AFTER_UPGRADE=" + (Test-Path $exe))
```

**改进建议**

```powershell
$arp2 = Get-ARP
Add-Content $out ("ARP_VERSION_AFTER_UPGRADE=" + $arp2.DisplayVersion)
Add-Content $out ("ARP_VERSION_OK=" + ($arp2.DisplayVersion -eq '1.0.1'))
Add-Content $out ("EXE_AFTER_UPGRADE=" + (Test-Path $exe))
```

#### 379. `scripts/verify_msi.ps1:52-55` · 中 / 缺陷

> 卸载目标完全依赖上一步可能不可靠的 ARP 项：`PSChildName` 未校验作用域/归属就直接传给 `msiexec /x`；若 ARP 缺失(或匹配到错误项)则整段卸载被静默跳过，`UNINSTALL_EXIT` 一行都不写，后面的 `EXE_AFTER_UNINSTALL=False`/`ARP_AFTER_UNINSTALL` 看起来就像“卸载干净”，把“产品根本没装上/ARP 查询失败”误判为通过；卸载退出码同样只记录不判断。建议显式记录 UNINSTALL_SKIPPED 并标记 FAIL，以“卸载前 EXE 存在”为前置断言，校验 `$p3.ExitCode` 仅 0/3010 视为成功，必要时用 `$msi101`(`msiexec /x "$msi101"`)作为回退卸载路径。

**现有代码**

```powershell
if ($arp2.PSChildName) {
    $p3 = Start-Process msiexec -ArgumentList "/x", $arp2.PSChildName, "/qn", "/l*v", "`"$logDir\uninstall.log`"" -Wait -PassThru
    Add-Content $out "UNINSTALL_EXIT=$($p3.ExitCode)"
}
```

**改进建议**

```powershell
if ($arp2.PSChildName) {
    $p3 = Start-Process msiexec -ArgumentList "/x", "`"$($arp2.PSChildName)`"", "/qn", "/norestart", "/l*v", "`"$logDir\uninstall.log`"" -Wait -PassThru
    Add-Content $out "UNINSTALL_EXIT=$($p3.ExitCode)"
    if ($p3.ExitCode -notin 0, 3010) { throw "卸载失败，msiexec 退出码 $($p3.ExitCode)" }
} else {
    Add-Content $out "UNINSTALL_SKIPPED=ARP not found"
}
```

#### 380. `scripts/verify_msi_user.ps1:3-4` · 高 / 可维护性

> 仓库根目录硬编码为 `C:\Users\Liyian\...`，脚本换用户、换机器或 CI 环境时会直接找不到 MSI(msiexec 1619)以及写不进 build 目录。建议用 `$PSScriptRoot` 推导仓库根目录，例如 `$root = Split-Path -Parent $PSScriptRoot`，并用 `Join-Path` 拼接产出路径；同时在使用前校验 `$msi100`/`$msi101` 是否存在。

**现有代码**

```powershell
$root   = "C:\Users\Liyian\WorkBuddy\python-pkg\pyenv-inspector"
$logDir = "$root\build"
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 381. `scripts/verify_msi_user.ps1:19` · 高 / 缺陷

> 写日志前没有确认 `$logDir`(build 目录)存在。若目录不存在，`Set-Content` 与后续所有 `Add-Content` 都只是非终止错误：在 `Continue` 策略下安装/升级/卸载仍会真实执行，但全程没有任何日志留存，属于静默丢失验证结果。建议先 `if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }`，并对首次写入做成功校验。

**现有代码**

```powershell
Set-Content -Path $out -Value "== perUser MSI 验证开始 $(Get-Date -Format 'HH:mm:ss') =="
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 382. `scripts/verify_msi_user.ps1:30` · 中 / 缺陷

> 脚本中大量中文字符串字面量(如这里的 `卸载 $name.lnk` 及输出的中文日志)。若该 .ps1 以 UTF-8 无 BOM 保存，Windows PowerShell 5.1 会按 ANSI 解析，导致字符串被乱码破坏：`Test-Path` 永远为 False(误报 UNINSTALL_LNK/DESKTOP 缺失)，日志也写成乱码。建议以 UTF-8 with BOM 保存脚本，或改用 `$([char]0x5378)...`/资源方式避免依赖源文件编码，并显式指定 `Add-Content -Encoding`。

**现有代码**

```powershell
Add-Content $out ("UNINSTALL_LNK=" + (Test-Path "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\$name\卸载 $name.lnk"))
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 383. `scripts/verify_msi_user.ps1:27` · 中 / 可维护性

> `(Get-ChildItem $installDir -Recurse -File -ErrorAction SilentlyContinue).Count` 在目录不存在或无权限时会静默得到空结果，`.Count` 计为 0，使 `FILE_COUNT=0` 与“目录确实为空”无法区分；同时脚本未校验 `$installDir` 这一 perUser 默认安装路径是否与 MSI 实际布局一致(路径含空格，布局变化时会整体误判)。建议先 `Test-Path $installDir` 并单独记录 `INSTALLDIR_EXISTS`，再统计文件数。

**现有代码**

```powershell
Add-Content $out ("FILE_COUNT=" + (Get-ChildItem $installDir -Recurse -File -ErrorAction SilentlyContinue).Count)
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 384. `app/core/collector.py:153-154` · 中 / 缺陷

> `requires` 只做了元素级校验, 没有校验容器类型。注释与文档都把 requires 视为列表, 但若采集结果中该字段意外为字符串(例如某些自定义 metadata 后端回传字符串), `for r in requires` 会逐字符迭代, 每个字符都是非空 str 且能通过 `isinstance(r, str) and r.strip()`, 于是被展开成一堆单字符伪依赖项, 污染依赖图且不报错。建议显式判断 `isinstance(requires, list)`, 非列表时退化为空列表(或视为解析异常)。

**现有代码**

```python
        version = p.get("version")
        requires = p.get("requires")
```

**改进建议**

```python
        version = p.get("version")
        requires = p.get("requires")
        if not isinstance(requires, list):
            requires = []
```

#### 385. `app/core/collector.py:63-64` · 中 / 缺陷

> 同名发行版合并时按 `len(requires)` 整体择一, 与上方注释宣称的“字段级合并、避免整条替换丢信息”不一致: 当两份元数据长度相同或较短的一份含独有依赖时, 独有的 `Requires-Dist` 会丢失。建议做保序并集合并, 既保留双方信息又不引入重复。

**现有代码**

```python
        if len(entry["requires"]) > len(old["requires"]):
            old["requires"] = entry["requires"]
```

**改进建议**

```python
        for req in entry["requires"]:
            if req not in old["requires"]:
                old["requires"].append(req)
```

#### 386. `app/core/collector.py:133` · 中 / 缺陷

> 结果识别条件过宽: 仅凭 dict 含 `packages` 键即认定为采集结果。目标环境中的 atexit/sitecustomize 钩子只要输出一行带 `packages` 键的无关 JSON, 就会被误选(且若其 packages 为列表, 后续校验也会通过), 从而返回错误的包列表。建议在采集脚本 payload 中加入唯一标记键(如 `"__pyenv_inspector__": 1`), 解析时要求该标记存在。

**现有代码**

```python
            if isinstance(candidate, dict) and "packages" in candidate:
```

**改进建议**

```python
            if (isinstance(candidate, dict)
                    and candidate.get("__pyenv_inspector__") == 1
                    and "packages" in candidate):
```

#### 387. `app/core/collector.py:30-31` · 低 / 可维护性

> 补全 user site-packages 失败被完全静默: `pass` 后没有任何诊断信息, 当 `site.getusersitepackages()` 抛错或返回异常路径时, `pip install --user` 安装的包会被静默漏采, 用户与上层都无法感知采集结果不完整。建议至少把异常信息写入 stderr(成功路径下 stderr 只在 returncode != 0 时才被读取, 不影响正常解析), 便于定位问题。

**现有代码**

```python
    if usp and usp not in sys.path:
        sys.path.append(usp)
```

**改进建议**

```python
    if usp and usp not in sys.path:
        sys.path.append(usp)
except Exception as _exc:
    # 不影响主流程, 但保留诊断信息(仅写入 stderr)
    print("warn: user site-packages unavailable: %r" % (_exc,), file=sys.stderr)
```

#### 388. `app/core/models.py:36-37` · 低 / 可维护性

> SOURCE_LABELS 是类级可变 dict(未加注解,dataclass 不会把它当作字段),所有实例与子类共享同一对象。目前只读访问,但任何调用方一旦写入(例如在现场扩展渠道文案)都会污染全部 InterpreterInfo 实例,且新渠道无法只影响单个实例。建议显式声明为 ClassVar 并改为只读映射(如 types.MappingProxyType),使误写立即失败、语义更清晰。

**现有代码**

```python
    SOURCE_LABELS = {
        "launcher": "Py 启动器",
```

**改进建议**

```python
    SOURCE_LABELS: ClassVar[Mapping[str, str]] = MappingProxyType({
        "launcher": "Py 启动器",
```

#### 389. `app/core/models.py:61-62` · 低 / 缺陷

> `self.version or "0"` 会把空版本(探测失败、probe_error 非空时很常见)当作合法版本 0 处理,于是它拿到 rank=1,配合 reverse=True 会排在所有真实版本之后、却排在真正“无法解析”的版本(rank=0)之前,与 docstring 承诺的“无法解析的版本排在最后”不一致。建议把空版本显式归入 rank=0。

**现有代码**

```python
        try:
            return (1, Version(self.version or "0"))
```

**改进建议**

```python
        if not self.version:
            return (0, Version("0"))
        try:
            return (1, Version(self.version))
```

#### 390. `app/core/models.py:241-244` · 低 / 缺陷

> 当 .condarc 写成 `channels: conda-forge`(标量而非列表)或 YAML 子集解析出其它类型时,这里静默返回空列表,而 error 字段仍为空,界面上会表现为“配置里没有频道”,排障成本高。建议对标量做单元素兼容,或在类型不符时把问题写回 error 字段。

**现有代码**

```python
    @property
    def channels(self) -> list[str]:
        v = self.data.get("channels")
        return [str(x) for x in v] if isinstance(v, list) else []
```

**改进建议**

```python
    @property
    def channels(self) -> list[str]:
        v = self.data.get("channels")
        if isinstance(v, list):
            return [str(x) for x in v]
        if isinstance(v, str) and v:
            return [v]
        return []
```

#### 391. `app/core/scc.py:34` · 低 / 可维护性

> `work` 的元素类型被写成 `tuple[str, object]`，导致下面 `for nxt in it` 处必须用 `# type: ignore[union-attr]` 才能通过类型检查。`object` 会屏蔽这一行的所有静态检查（例如以后误把非迭代对象放进 work 也发现不了），且该 ignore 的错误码本身也不准确（迭代 `object` 通常报 `attr-defined`/`misc`，开启 `warn_unused_ignores` 时还会产生无效 ignore 警告）。建议改为精确类型 `Iterator[str]`（`from collections.abc import Iterator`），并删除该 `type: ignore`。

**现有代码**

```python
        work: list[tuple[str, object]] = [(root, iter(adj.get(root, ())))]
```

**改进建议**

```python
        work: list[tuple[str, Iterator[str]]] = [(root, iter(adj.get(root, ())))]
```

#### 392. `app/core/scc.py:73-75` · 低 / 可维护性

> `find_cycles` 的形参使用裸 `dict`/`list`，完全没有描述元素结构，调用方无法从签名得知 `packages` 的键就是节点 key、`edges` 的元素需要提供 `source_key`/`target_key`。建议补全类型（如 `dict[str, PackageInfo]`、`list[DepEdge]`，可用 `TYPE_CHECKING` 导入避免运行时耦合），否则后续传入 tuple/dict 形式的边时只能在运行时抛 `AttributeError`。

**现有代码**

```python
def find_cycles(
    packages: dict, edges: list
) -> list[list[str]]:
```

**改进建议**

```python
def find_cycles(
    packages: dict[str, "PackageInfo"], edges: list["DepEdge"]
) -> list[list[str]]:
```

#### 393. `app/core/scc.py:77-79` · 低 / 可维护性

> 邻接表由 `edges` 全量构建，未按 `packages` 过滤端点；而 `strongly_connected_components` 的入口节点只有 `packages.keys()`，一旦某条边的端点不在 `packages` 中，它会被 DFS 顺带遍历并进入 SCC，从而被当作循环组/自环返回给调用方。当前唯一调用方 `analyzer.analyze` 会先为缺失 target 生成幽灵节点，所以暂未触发；但同项目 `layout._active_adjacency` 采用了 `if e.source_key in adj and e.target_key in adj` 的过滤策略，两处行为不一致。建议这里同样做端点过滤，或在 docstring 中显式声明“所有边端点必须出现在 packages 中”的前置条件。

**现有代码**

```python
    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        adj[e.source_key].append(e.target_key)
```

**改进建议**

```python
    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if e.source_key in packages and e.target_key in packages:
            adj[e.source_key].append(e.target_key)
```

#### 394. `app/core/env_manager.py:343-348` · 高 / 缺陷

> 超时形同虚设且超时/启动失败时子进程残留：`for line in proc.stdout` 会一直阻塞到管道 EOF，`timeout` 只作用于其后的 `proc.wait()`（此时进程多半已退出，实际不再计时）；若子进程挂起且不产出输出，会无限阻塞。另外 `proc.wait(timeout=...)` 抛 `TimeoutExpired` 时没有 kill 子进程、也没有关闭 `proc.stdout`，会造成孤儿进程与句柄泄漏；`subprocess.Popen` 的 `FileNotFoundError`（conda_exe/python_exe 路径不存在）同样未包装，违背模块文档"所有失败抛 EnvManagerError"的契约。建议：用看门狗线程/截止时间在读取循环中强制超时，超时时 `proc.kill()` 并在 `finally` 中关闭 stdout；同时把 `Popen` 的 `OSError` 与 `TimeoutExpired` 包装为 `EnvManagerError`。

**现有代码**

```python
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            collected.append(line)
            on_output(line)
    code = proc.wait(timeout=timeout)
```

**改进建议**

```python
    try:
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                collected.append(line)
                on_output(line)
        code = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        proc.wait()
        raise EnvManagerError(
            f"命令执行超时({timeout}s): {' '.join(cmd)}") from exc
    finally:
        proc.stdout.close()
```

#### 395. `app/core/env_manager.py:223-226` · 高 / 缺陷

> sha256 校验分支逻辑倒置，跳过校验的分支是死代码：`download_file` 抛出的错误信息固定含"下载失败"，sha256 不匹配的错误含"校验失败"，两者都会命中 `raise` 直接中断安装；`on_output("警告: 无法下载校验文件, 跳过 sha256 校验")` 永远不可达。后果是只要 .sha256 文件下载失败（且该文件仅从 `_MIRROR_TEMPLATES[0]` 单一源获取，未做多镜像回退），即使安装包已从其他镜像成功下载也无法安装。此外 `open(sha_file, ...)` 未使用 `with`，异常路径下句柄泄漏；若校验文件内容为空，`split()[0]` 还会抛 `IndexError`。

**现有代码**

```python
        except EnvManagerError as exc:
            if "校验失败" in str(exc) or "下载失败" in str(exc):
                raise
            on_output("警告: 无法下载校验文件, 跳过 sha256 校验")
```

**改进建议**

```python
        try:
            download_file(sha_url, sha_file)
        except EnvManagerError:
            on_output("警告: 无法下载校验文件, 跳过 sha256 校验")
        else:
            with open(sha_file, encoding="utf-8") as fh:
                parts = fh.read().split()
            if not parts:
                on_output("警告: 校验文件内容为空, 跳过 sha256 校验")
            else:
                expected = parts[0].lower()
                if _sha256_of(archive) != expected:
                    raise EnvManagerError(
                        "文件校验失败(sha256 不匹配), 已自动删除损坏的下载。\n"
                        "请重试或检查网络环境。")
                on_output("校验通过")
```

#### 396. `app/core/env_manager.py:386-389` · 高 / 安全

> 删除保护只校验 `name` 字符串，实际删除目标用的是调用方传入的 `env_path`，二者未做一致性校验：当 `name` 合法（如 "myenv"）而 `env_path` 指向 `conda_root/base` 或其他任意目录时，占用检测与 `conda env remove -p`、以及末尾兜底的 `shutil.rmtree(env_path)` 都会作用于该路径，可能误删 base 或任意目录。另外此函数中 `conda_root` 参数除接收外完全未被使用。建议将 `env_path` 规范化后校验其位于 `os.path.join(conda_root, "envs")` 之下且不等于 base 路径，否则抛 `EnvManagerError`。

**现有代码**

```python
    if name.lower() == "base":
        raise EnvManagerError("base 是 conda 的基础环境, 不允许删除。")
    validate_env_name(name)
    env_path = os.path.normpath(os.path.abspath(env_path))
```

**改进建议**

```python
    validate_env_name(name)
    env_path = os.path.normpath(os.path.abspath(env_path))
    envs_root = os.path.normpath(os.path.abspath(os.path.join(conda_root, "envs")))
    norm_expect = os.path.normcase(env_path)
    if (name.lower() == "base"
            or not norm_expect.startswith(os.path.normcase(envs_root) + os.sep)
            or os.path.basename(norm_expect) != name.lower()):
        raise EnvManagerError(
            f"环境路径校验失败, 拒绝删除: {env_path}")
```

#### 397. `app/core/env_manager.py:81-82` · 中 / 缺陷

> 托管标记判定在 POSIX 上不成立：标记文件始终写在环境根目录（见 `_write_marker` 与 `list_managed_interpreters`），而这里取的是可执行文件所在目录。Windows 下 `dirname(env/python.exe) == env` 成立，但 POSIX 下 `dirname(env/bin/python) == env/bin`，导致永远返回 False；`remove_interpreter` 传入的正是 `env/bin/python`，于是 POSIX 上托管解释器永远无法删除。建议先判断传入路径是目录还是可执行文件，再向上级目录查找标记。

**现有代码**

```python
    marker = os.path.join(os.path.dirname(path), MANAGED_MARKER)
    return os.path.isfile(marker)
```

**改进建议**

```python
    base = path if os.path.isdir(path) else os.path.dirname(path)
    for cand in (base, os.path.dirname(base)):
        if os.path.isfile(os.path.join(cand, MANAGED_MARKER)):
            return True
    return False
```

#### 398. `app/core/env_manager.py:277-278` · 中 / 缺陷

> `shutil.rmtree(env_dir)` 可能抛出 `PermissionError`/`OSError`（文件被占用、权限不足、路径已不存在等），未经包装直接抛给调用方，破坏了模块约定"失败抛 EnvManagerError(message 为人读文本)"，UI 层无法展示友好提示（`find_processes_using_dir` 也明确说明探测失败时依赖这里兜底）。建议捕获并转换为 `EnvManagerError`。

**现有代码**

```python
    on_output("正在删除解释器目录…")
    shutil.rmtree(env_dir)
```

**改进建议**

```python
    on_output("正在删除解释器目录…")
    try:
        shutil.rmtree(env_dir)
    except OSError as exc:
        raise EnvManagerError(
            f"删除失败(可能文件被占用或权限不足): {exc}\n路径: {env_dir}") from exc
```

#### 399. `app/core/env_manager.py:486` · 低 / 可维护性

> `tool` 与 `op` 两个参数在函数体内从未被引用（所有分支只基于 `output.lower()` 判断），属于无效参数，容易让人误以为错误翻译会按工具/操作做区分。建议删除这两个参数并同步修改全部调用点，或真正按 `tool`/`op` 限定匹配范围（例如 conda 的 notfound 提示不应出现在 pip 场景）。

**现有代码**

```python
def translate_error(tool: str, op: str, output: str) -> str:
```

**改进建议**

```python
def translate_error(output: str) -> str:
```

#### 400. `app/demo.py:46` · 中 / 文档

> 文档与数据不一致: 此处 docstring 声称 ujson 的标记是“仅限非 Windows”，但实际标记是 `python_version < '3.0'`(3.12 下恒假且平台无关)，且紧邻该依赖的注释也写明“平台无关, 各 OS 演示结果一致”。演示说明会误导读者对“环境标记不适用”场景的理解，建议与实现对齐。

**现有代码**

```python
    - 环境标记不适用: ujson 仅限非 Windows
```

**改进建议**

```python
    - 环境标记不适用: ujson 的 python_version < '3.0' 恒假(平台无关)
```

#### 401. `app/demo.py:130` · 中 / 缺陷

> 回退逻辑会把环境根目录当成解释器可执行文件路径。`CondaEnvironment.path` 明确是“环境根路径”(如 C:\\Demo\\Miniconda3\\envs\\ml)，当 `interpreter` 为空时，生成的 InterpreterInfo.path 会是一个目录而非 python.exe，导致按路径注册/联动或后续探测全部错位。当前唯一调用方 main_window.load_demo 有 `if env.interpreter and ...` 保护，所以尚未触发，但该兜底本身是错误语义。建议直接使用 `env.interpreter`(或按平台拼出 `python.exe`/`bin/python`)，不要退化为目录路径。

**现有代码**

```python
            path=env.interpreter or env.path, version=version,
```

**改进建议**

```python
            path=env.interpreter, version=version,
```

#### 402. `app/demo.py:134` · 低 / 缺陷

> `rsplit('.', 1)[0]` 隐含“版本号至少三段”的假设：若 CondaEnvironment.python_version 是 `"3.12"`，这里会得到 `"3"` 而不是主版本 `"3.12"`；若为单段 `"3"` 则会退化为空串。虽然演示数据都是三段版本、且 `or "3.12.0"` 已兜住空值，但该函数接受任意 CondaEnvironment，建议显式取前两段更稳健。

**现有代码**

```python
        python_version=version.rsplit(".", 1)[0],
```

**改进建议**

```python
        python_version=".".join(version.split(".")[:2]),
```

#### 403. `app/core/analyzer.py:41-43` · 低 / 可维护性

> `InstalledPackage` 在本文件中从未被引用(全项目只有 main_window 从 analyzer 导入 `analyze`),属于未使用的导入,建议删除,保持导入表精确。

**现有代码**

```python
    EnvironmentSnapshot,
    InstalledPackage,
    PackageInfo,
```

**改进建议**

```python
    EnvironmentSnapshot,
    PackageInfo,
```

#### 404. `app/core/analyzer.py:156-157` · 中 / 缺陷

> 解析失败时用首个 token 直接做 target_key/target_display 不可靠:该 token 可能包含运算符或括号(如缺逗号的 `numpy>=1.0 <2.0`、`(>=1.0)`、`foo[bar]`)。analyze() 的挂接阶段会为所有边的 target 生成 installed=False 的幽灵节点,于是图上会出现名为 `numpy>=1.0`、`foo[bar]` 之类并不存在的包,且其 key 带 `[`、`>` 等字符会影响后续查找/展示。建议先用名字正则校验 token,只有合法 PEP 508 名字才作为 target,否则使用固定占位(如 `?invalid?`)并避免为其生成幽灵节点。

**现有代码**

```python
            target_key=canonicalize_name(first_token) or "?invalid?",
            target_display=first_token,
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 405. `app/core/analyzer.py:73-75` · 低 / 缺陷

> 同 canonical name 的重复记录只按 requires 长度择优,完全没有比较/合并 version:collector 只按 `name.strip().lower()` 去重(如 `foo_bar` 与 `foo-bar` 会同时进入快照),若被保留那条的 version 为空而被丢弃那条有版本,所有指向该包的边都会因空版本被判为 UNKNOWN;被丢弃记录的 Requires-Dist 也可能静默丢失。建议像 collector 一样做字段级合并(version 取非空、requires 取更长),并在两处版本不一致时追加 warning(需把 `warnings` 的初始化提前)。

**现有代码**

```python
        old = packages.get(key)
        if old is None or len(entry.requires_raw) > len(old.requires_raw):
            packages[key] = entry
```

**改进建议**

```python
        old = packages.get(key)
        if old is None:
            packages[key] = entry
            continue
        # 与 collector 一致: 字段级合并, 避免丢失版本或依赖声明
        if not old.version and entry.version:
            old.version = entry.version
        if len(entry.requires_raw) > len(old.requires_raw):
            old.requires_raw = entry.requires_raw
```

#### 406. `app/main_window.py:459-460` · 高 / 缺陷

> MainWindow 的线程回收路径存在同类风险：演示模式排空线程时未检查 wait(15000) 返回值，closeEvent 中也未检查 wait(1000) 返回值；超时后线程仍在运行却被 deleteLater/父对象析构，会触发 “QThread: Destroyed while thread is still running” 崩溃。此外 demo 路径会同步阻塞 GUI 最长 45s；closeEvent 对未运行事件循环的 QThread 调 quit() 无效，terminate() 强杀也可能留下不一致状态。建议改为连接 finished→deleteLater/延迟回收，超时不要销毁线程，必要时 event.ignore() 保留窗口，避免同步阻塞。

**现有代码**

```python
                if worker.isRunning():
                    worker.wait(15000)
```

**改进建议**

```python
                if worker.isRunning() and not worker.wait(15000):
                    # 超时: 交给线程结束后自毁, 不能在运行中销毁 QThread
                    worker.finished.connect(worker.deleteLater)
                    continue
```

#### 407. `app/main_window.py:424-427` · 中 / 缺陷

> 环境根目录推算对 Windows 虚拟环境不成立:venv 的解释器位于 `<env>\Scripts\python.exe`,这里只在非 Windows 上去掉一层 `bin`,会返回 `<env>\Scripts`。该结果被用于 `manage_page.set_current_env_dir(...)` 的删除保护,导致保护目录指向错误位置(保护失效或误保护)。建议对 `bin`/`Scripts` 统一剥离一层。

**现有代码**

```python
        d = os.path.dirname(os.path.normpath(python_path))
        if os.name != "nt" and os.path.basename(d) == "bin":
            return os.path.dirname(d)
        return d
```

**改进建议**

```python
        d = os.path.dirname(os.path.normpath(python_path))
        if os.path.basename(d).lower() in ("bin", "scripts"):
            return os.path.dirname(d)
        return d
```

#### 408. `app/main_window.py:368-370` · 中 / 缺陷

> 演示模式下点“刷新”会调用 `_load_demo()`,而它总是重建**默认**演示快照并 `_apply_snapshot` 跳转到包列表页。若用户是通过双击演示 conda 环境进入的(`_snapshots` 中存的是对应环境的 demo 快照),刷新后会丢失当前正在查看的环境,跳到无关的默认演示环境。建议按当前 `interpreter` 重建对应演示快照,而不是整体重新加载演示数据。

**现有代码**

```python
        if getattr(self._snapshot, "is_demo", False):
            self._load_demo()
            return
```

**改进建议**

```python
        if getattr(self._snapshot, "is_demo", False):
            # 仅重建当前演示环境, 避免跳回默认演示快照
            self._reload_demo_snapshot(self._snapshot.interpreter)
            return
```

#### 409. `app/main_window.py:74` · 低 / 缺陷

> 齿轮图标绘制有误:该循环的起点 y 已经是 `y + dy`(即与终点相同),因此 `(0, c)`、`(size, c)` 两条线长度为 0(只剩 RoundCap 圆点),`(c, size)` 则变成贯穿整个图标的竖线,而不是四个齿。建议显式给出四条短齿的起止点。

**现有代码**

```python
        for dx, dy in ((c, 0), (c, size), (0, c), (size, c)):
```

**改进建议**

```python
        for sx, sy, ex, ey in ((c, 0, c, 3), (c, size - 3, c, size),
                               (0, c, 3, c), (size - 3, c, size, c)):
            painter.drawLine(x + int(sx), y + int(sy), x + int(ex), y + int(ey))
```

#### 410. `app/core/layout.py:219` · 高 / 缺陷

> 斥力量纲与 FR 公式不一致:经典 FR 斥力为 k²/d,这里先算 k²/d² 再乘单位方向向量,实际斥力只有 k²/d²。与下面正确的引力 d²/k 联立,平衡距离会退化为 k^{3/4}(width=1500/height=850/18 个节点时 k≈306,平衡距离仅 ≈73px),节点会明显挤在一起,与 docstring 中“理想边长 k”+1.15 松弛系数的意图不符。建议改为除以一次距离。

**现有代码**

```python
    force = (k * k) / dist2
```

**改进建议**

```python
    force = (k * k) / dist
```

#### 411. `app/core/layout.py:175-176` · 中 / 缺陷

> 网格分支以非对称方式调用 _repel,依赖“反向遍历时另一侧也被处理”来补齐双向斥力;但两个坐标完全重合时(典型场景:边界 clamp 把多个节点压到同一角点),_repel 的兜底会给出同向的 (0.5, 0.5) 偏移,两个节点收到完全相同的推力,永远无法分开,会一直重叠。另外这种“每对处理两次”的写法也让网格分支的斥力计算量翻倍。建议网格分支对每对只处理一次并传 symmetric=True,让重合兜底产生相反方向。

**现有代码**

```python
                        for b in grid.get((gx + dx, gy + dy), ()):
                            _repel(a, b, pos, disp, k)
```

**改进建议**

```python
                        for b in grid.get((gx + dx, gy + dy), ()):
                            if a >= b:   # 每对只处理一次, 保证重合节点得到反向斥力
                                continue
                            _repel(a, b, pos, disp, k, symmetric=True)
```

#### 412. `app/core/layout.py:201-202` · 中 / 缺陷

> 边界只留 24px,但节点卡片的实际尺寸是宽度 104~240px、高度 46px(NodeItem.boundingRect 以左上角为原点),且布局坐标是节点左上角语义。被 clamp 到 x=width-24 的节点右边缘会超出画布最多约 216px,靠右/靠下的节点还会被压在同一角点上(进而触发上面提到的重合节点无法分离问题)。建议按最大节点尺寸留边,或把 clamp 改为按节点右上/左下角约束。

**现有代码**

```python
            nx = min(max(pos[a][0] + dx / d * step, 24.0), width - 24.0)
            ny = min(max(pos[a][1] + dy / d * step, 24.0), height - 24.0)
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 413. `app/core/layout.py:155` · 中 / 缺陷

> width/height 未做任何校验:传入 0(或负值)时 k=0,引力分支 (dist*dist)/k 会直接 ZeroDivisionError;width/height < 48 时 min(max(x, 24.0), width-24.0) 的上下界反转,所有节点会被固定到 width-24(负坐标)。建议在函数入口收敛参数(并同时用于上面的节点尺寸留边)。

**现有代码**

```python
    k = 1.15 * math.sqrt((width * height) / max(n, 1))
```

**改进建议**

```python
    width = max(float(width), 480.0)
    height = max(float(height), 300.0)
    k = 1.15 * math.sqrt((width * height) / max(n, 1))
```

#### 414. `app/core/layout.py:37` · 低 / 缺陷

> 该宽度估算与 UI 侧并不一致:NodeItem 用 QFontMetrics 实测文本宽度(超 24 字符先 elide),宽度上限随字形而变;这里固定按 len(name) 累计 7.6px/字符并硬性封顶 240。对 ≤24 字符但字形较宽的包名(如大写字母/宽字母组成)会低估实际卡片宽度,超过 gap_x=34 时同层仍会重叠,与“长名节点不再重叠”的承诺相悖。建议要么放宽系数/留出更保守的余量,要么由 UI 侧把实测宽度传入布局。

**现有代码**

```python
    return min(max(104.0, len(name) * 7.6 + 28.0), 240.0)
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 415. `app/core/layout.py:87-90` · 低 / 可维护性

> 此兜底不会产生任何效果:level 在初始化时已是全 0,这里把未访问分组的层级再次赋 0 是空操作。SCC 已保证凝聚图无环,循环结束后 visited 恒等于 len(comps)。建议删除该分支,或改为在真的检测到异常时记录/抛出,以免误导后续维护者以为这里有容错。

**现有代码**

```python
    if visited != len(comps):
        for ci in range(len(comps)):
            if indeg[ci] > 0:
                level[ci] = 0
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 416. `app/ui/analysis_page.py:235` · 高 / 缺陷

> 取消后台布局任务后没有关闭忙碌遮罩。`BusyOverlay` 只会在 `stop()` 中隐藏（见 widgets.py 228 行），而 `_cancel_pending_layout()` 只断开信号，随后走同步布局分支时不会调用 `busy.stop()`。场景：力导向布局（>60 包）计算中，用户切到「分层布局」或载入新环境 → 遮罩与 spinner 永远留在界面上，整个页面被挡住。建议在取消任务后补一次 `busy.stop()`。

**现有代码**

```python
        self._cancel_pending_layout()  # 切布局/换数据时丢弃旧的后台计算
```

**改进建议**

```python
        self._cancel_pending_layout()  # 切布局/换数据时丢弃旧的后台计算
        if self.busy.isVisible():
            self.busy.stop()  # 旧任务的 done/failed 已断开, 遮罩需在此显式关闭
```

#### 417. `app/ui/analysis_page.py:256-259` · 中 / 缺陷

> 回收逻辑存在两处问题：1) `isRunning()` 判断与 `finished.connect(deleteLater)` 之间存在竞态——线程恰好在这两步之间结束，`finished` 已发射，`deleteLater` 永远不会被调用，QThread 对象泄漏（且它是页面的子对象，一直存活）；2) 只是断开信号而不请求中断，`force_layout` 会继续占用一个 CPU 线程，反复切换布局会并行跑多个线程。建议在创建时就连接 `finished → deleteLater`（并配合去重），同时调用 `requestInterruption()` 并在布局循环里检查中断标记；另外 worker 的 parent 是页面本身，页面在计算中被销毁时会触发「QThread: Destroyed while thread is still running」崩溃，也需一并规避。

**现有代码**

```python
        if old.isRunning():
            old.finished.connect(old.deleteLater)  # 延迟回收, 不销毁运行中线程
        else:
            old.deleteLater()
```

**改进建议**

```python
        old.requestInterruption()  # 让 _compute_layout 尽快退出 (需在布局循环中检查)
        if old.isRunning():
            # finished 在创建时已统一连接到 deleteLater, 此处不要再条件连接, 避免竞态/重复连接
            pass
        else:
            old.deleteLater()
```

#### 418. `app/ui/analysis_page.py:342-343` · 低 / 可维护性

> `setRowCount(len(problems))` 在循环前后各调用了一次，第二次是重复语句（首次调用已完成行数设置），可直接删除。

**现有代码**

```python
        self.conflict_table.setRowCount(len(problems))
        if problems:
```

**改进建议**

```python
        if problems:
```

#### 419. `app/ui/analysis_page.py:19` · 低 / 可维护性

> 存在未使用的导入：`FlowLayout`、`make_badge`（本文件只用到 `BusyOverlay`，`StatCard` 在 `_make_stat` 内部单独导入），以及第 7 行导入的 `Signal`。这些属于死代码，建议清理以免误导。

**现有代码**

```python
from .widgets import BusyOverlay, FlowLayout, make_badge
```

**改进建议**

```python
from .widgets import BusyOverlay
```

#### 420. `app/core/scanner.py:238-239` · 高 / 缺陷

> `json.loads` 的结果未被校验类型。若某个候选可执行文件（例如伪装/错误的 `python.exe`、PowerShell 包装脚本等）输出了合法但非对象的 JSON（`[1,2]`、`123`、`"x"`），`data.get(...)` 会抛出 `AttributeError`，而下面的 `except` 只捕获了 `JSONDecodeError/IndexError/KeyError/TypeError`，异常会一路冒出 `probe_interpreter`，导致整次扫描中断而不是仅跳过该候选。建议显式校验 `isinstance(data, dict)`（或至少把 `AttributeError` 加入捕获列表）。

**现有代码**

```python
        data = json.loads(lines[-1])
        info.version = str(data.get("version", ""))
```

**改进建议**

```python
        data = json.loads(lines[-1])
        if not isinstance(data, dict):
            info.probe_error = "探测输出不是 JSON 对象"
            return info
        info.version = str(data.get("version", ""))
```

#### 421. `app/core/scanner.py:83` · 中 / 缺陷

> POSIX 下这里只用原路径去重，未做符号链接归一。`/usr/bin/python3`、`/usr/bin/python3.12`、`/usr/local/bin/python3` 常常是同一二进制的软链，会被当成多个候选分别启动探测（每个候选一次子进程，最坏 20s 超时），最后的 `if info not in interpreters` 也无法兜底——`InterpreterInfo` 是默认 `eq` 的 dataclass，`path` 参与比较，软链差异使对象必然不相等，结果列表里会出现多条同一解释器。建议用 `os.path.realpath(full)` 作为去重键（显示路径仍保留原始 `full`）。

**现有代码**

```python
        norm = os.path.normcase(full) if _is_windows() else full
```

**改进建议**

```python
        # 去重键用真实路径，避免 POSIX 软链造成同一解释器重复探测/重复展示
        norm = os.path.normcase(os.path.realpath(full)) if _is_windows() else os.path.realpath(full)
```

#### 422. `app/core/scanner.py:212` · 中 / 安全

> `path` 来自 PATH、HKCU 注册表（`Software\Python\PythonCore\*\InstallPath\ExecutablePath` 可被当前用户任意改写）以及用户可写的 `%LOCALAPPDATA%\Microsoft\WindowsApps`，这里会无条件直接执行。`-I` 只隔离 Python 的导入路径，不提供任何信任保证；如果本工具被以管理员权限启动（扫描全机器解释器的常见场景），就会以高权限执行用户可写位置的任意可执行文件，构成提权面。建议至少对非系统可信来源的候选做一次明确标注/交互确认，或在工作线程用最低权限探测，并把实际执行的路径写进 `ScanReport.log` 便于追溯。

**现有代码**

```python
    argv = [path, "-I", "-c", PROBE_SCRIPT]
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 423. `app/core/scanner.py:173` · 中 / 缺陷

> WindowsApps 下的 `python*.exe` 多为 App Execution Alias（0 字节 reparse point），当对应 Store 包未安装时 `os.path.isfile` 仍返回 True，但一旦执行就会拉起 Microsoft Store 页面，而不是快速失败；这会给用户带来意外弹窗，也会在 `log` 里留下难解释的“退出码”。建议在加入候选前过滤掉 `os.stat(hit).st_size == 0`（或 reparse tag 为 APPEXECLINK 且目标包不存在）的别名。

**现有代码**

```python
        for hit in _glob.glob(os.path.join(store_dir, "python*.exe")):
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 424. `app/core/scanner.py:111-112` · 低 / 可维护性

> py 启动器查询失败、注册表分支打开失败、conda `envs` 目录 `listdir` 失败（第 5 步的 `except OSError: pass`）都被静默丢弃，`ScanReport.log` 只会显示“扫描完成”，无法解释为什么某些已安装解释器缺失。建议把这些非致命错误累积到一个列表并附加到 `ScanReport.log`，而不是直接 `pass`。

**现有代码**

```python
        except (OSError, subprocess.TimeoutExpired):
            pass
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 425. `app/core/scanner.py:136-137` · 低 / 风格

> `import glob as _glob` 被写在循环体内（第 6 步 Store 扫描处再次重复），与文件顶部的集中导入风格不一致，也容易被误认为循环里有额外开销；建议把 `import glob` 提到模块顶部统一使用。

**现有代码**

```python
    for pattern in _common_patterns():
        import glob as _glob
```

**改进建议**

```python
    for pattern in _common_patterns():
```

#### 426. `app/ui/conda_page.py:75-78` · 低 / 可维护性

> `load_content` 每次都向 `self._layout` 末尾追加 label/holder，没有先清理上一次的动态内容（头部两行与构造期的 note 是固定的）。当前调用点每次扫描都新建 `_ConfigCard` 所以不会立刻出错，但卡片一旦被复用或改为增量刷新（例如只重读某个 .condarc），就会出现重复的键值行/重复错误标签。建议进入方法时先移除索引 0（头部）之后的子控件。

**现有代码**

```python
    def load_content(self, cf) -> None:
        """填充配置摘要(cf: CondaConfigFile)。"""
        if not cf.exists:
            return
```

**改进建议**

```python
    def load_content(self, cf) -> None:
        """填充配置摘要(cf: CondaConfigFile)。"""
        # 先清空上一次填充的动态内容, 只保留索引 0 的头部行
        while self._layout.count() > 1:
            item = self._layout.takeAt(1)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        if not cf.exists:
            return
```

#### 427. `app/ui/conda_page.py:258` · 低 / 缺陷

> `info.version` 来自 `conda --version`，只有找到可执行文件时才有值。当扫描仅从文件系统发现 root/envs（未找到 conda 可执行文件）时，这里会显示「未检测到」，与下方「发现 N 个 conda 环境」的副标题自相矛盾。建议按是否存在 roots/envs 区分「未检测到」与「未知」。

**现有代码**

```python
        self._chip_version.set_value(info.version or "未检测到")
```

**改进建议**

```python
        if info.version:
            self._chip_version.set_value(info.version)
        elif info.roots or info.envs:
            self._chip_version.set_value("未知(未找到 conda 可执行文件)")
        else:
            self._chip_version.set_value("未检测到")
```

#### 428. `app/ui/conda_page.py:331-334` · 低 / 可维护性

> `index` 参数未使用，实际依赖 `currentRow()`；而 `name_item.setData(Qt.UserRole, env.path)` 写入后从未被读取。行号与 `info.envs` 的隐式顺序耦合在将来启用排序/过滤（`setSortingEnabled`、隐藏行）时会激活错误的环境。建议直接用 `index.row()`（或 UserRole 中的 path）定位环境。

**现有代码**

```python
    def _on_env_double_clicked(self, index) -> None:
        env = self._current_env()
        if env is not None:
            self.environment_activated.emit(env.path)
```

**改进建议**

```python
    def _on_env_double_clicked(self, index) -> None:
        if not index.isValid() or self._conda_info is None:
            return
        row = index.row()
        if 0 <= row < len(self._conda_info.envs):
            self.environment_activated.emit(self._conda_info.envs[row].path)
```

#### 429. `app/ui/conda_page.py:5-6` · 低 / 文档

> 模块文档提到的「查看 pip 包」按钮在类中并不存在（只有双击环境这一条路径），且 `environment_activated` 的注释写的是“激活环境”，实际语义是“进入该环境的 pip 包分析流水线”。文档/注释与实现不一致会误导后续接线与用户操作，建议同步修正。

**现有代码**

```python
- 双击环境行(或「查看 pip 包」按钮)直接接入既有
  解释器 → 包采集 → 依赖分析流水线
```

**改进建议**

```python
- 双击环境行直接接入既有解释器 → 包采集 → 依赖分析流水线
```

#### 430. `app/ui/interpreters_page.py:5` · 低 / 可维护性

> `os` 在整个文件中未被引用(本文件没有 `os.` 调用),属于无用的死导入,建议删除。

**现有代码**

```python
import os
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 431. `app/ui/interpreters_page.py:16` · 低 / 可维护性

> `IconLabel` 在本文件从未使用(图标改由 `_PyIcon` 自绘),属于死导入,建议从导入列表中移除。

**现有代码**

```python
from .widgets import ElidedLabel, FlowLayout, IconLabel, make_badge
```

**改进建议**

```python
from .widgets import ElidedLabel, FlowLayout, make_badge
```

#### 432. `app/ui/interpreters_page.py:253-255` · 中 / 缺陷

> 双击时 `interpreter_selected` 会被重复发出:Qt 双击序列为 release1(emit clicked) → press2 → doubleClick(`_on_card_activated` 又调用 `_on_card_clicked`) → release2(再次 emit clicked),一次双击实际会发出 2~3 次“选中”信号。若下游在选中回调里做耗时操作(如读取包元数据),会被重复触发。建议记录选择是否真正发生变化,仅在变化时 emit,例如:
>
> ```python
> changed = self._current is not info
> self._current = info
> ...
> if changed:
>     self.interpreter_selected.emit(info)
> ```
> 同时 `_on_card_activated` 中可先判断 `self._current is not info` 再调用 `_on_card_clicked`。

**现有代码**

```python
    def _on_card_clicked(self, info: InterpreterInfo) -> None:
        self._current = info
        for card in self._cards:
```

**改进建议**

```python
    def _on_card_clicked(self, info: InterpreterInfo) -> None:
        changed = self._current is not info
        self._current = info
        for card in self._cards:
```

#### 433. `app/ui/interpreters_page.py:235-237` · 中 / 缺陷

> 重新扫描时这里静默清空了 `_current` 并禁用按钮,却不对外发出任何“选择已失效”的通知。本页对外暴露了 `interpreter_selected` 作为选择状态变更通道,任何按该信号维护自身选中项的组件在重扫后仍会持有已删除的 `InterpreterInfo`。建议在清空前有选中项时补发一次选择变更(可为 `None`),或新增 `selection_cleared` 信号。

**现有代码**

```python
        self._current = None
        self.load_button.setEnabled(False)
        self.hint_label.setText("")
```

**改进建议**

```python
        had_selection = self._current is not None
        self._current = None
        self.load_button.setEnabled(False)
        self.hint_label.setText("")
        if had_selection:
            self.interpreter_selected.emit(None)
```

#### 434. `app/ui/interpreters_page.py:227-228` · 低 / 缺陷

> `text` 默认是空串,因此调用方不带文本的 `set_scanning(False)`(如采集完成/失败后)会把状态行里“共发现 N 个可用解释器”的统计文本一并清空,页面状态信息丢失。建议把 `text` 默认值改为 `None` 并仅在传入非空文本时刷新文案。

**现有代码**

```python
        self.rescan_button.setEnabled(not on)
        self.status_label.setText(text)
```

**改进建议**

```python
        self.rescan_button.setEnabled(not on)
        if text is not None:
            self.status_label.setText(text)
```

#### 435. `app/ui/interpreters_page.py:205-206` · 低 / 可维护性

> `FlowLayout(container, ...)` 在构造时已把自身安装到 `container` 上(`QLayout.__init__(parent)` 会调用 `parent->setLayout(this)`),再调用一次 `container.setLayout(...)` 是冗余的,运行时会打印 “Attempting to set QLayout ... which already has a layout” 的 Qt 警告。建议删除 `setLayout` 这一行。

**现有代码**

```python
        self._flow = FlowLayout(container, margin=2, spacing=16)
        container.setLayout(self._flow)
```

**改进建议**

```python
        self._flow = FlowLayout(container, margin=2, spacing=16)
```

#### 436. `app/ui/interpreters_page.py:104` · 低 / 缺陷

> 卡片宽度被 `setFixedWidth(272)` 锁死,右侧文本列可用宽度只有约 190px;而 `ElidedLabel` 未覆写 `sizeHint`/`minimumSizeHint`,`QLabel` 的最小尺寸提示就是完整路径文本宽度。长路径会把布局最小宽度撑到卡片宽度之外,导致路径文本溢出卡片边界被硬裁切(而不是按设计省略显示),甚至挤压徽章行。建议在卡片内显式约束该标签宽度,例如设置水平 `QSizePolicy.Ignored` 与 `setMinimumWidth(0)`(或 `setMaximumWidth(...)`),让 `resizeEvent` 里的省略逻辑真正生效。

**现有代码**

```python
        path_label = ElidedLabel(info.path)
```

**改进建议**

```python
        path_label = ElidedLabel(info.path)
        path_label.setMinimumWidth(0)
        path_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
```

#### 437. `app/ui/theme.py:70` · 中 / 可维护性

> 全局 `outline: none` 会去掉 Qt 的焦点框（键盘可见性），而后面的 `QPushButton:focus { border-color }` 对 primary 按钮完全无效——primary 变体显式写了 `border: none`，没有边框可变色；`QTabBar::tab:focus` 也不是 Qt 支持的子控件伪状态（tab 仅支持 :selected/:hover/:disabled 等），属于无效规则。结果是纯键盘操作时（如 QToolButton#navButton、QTableView 单元格）无法看出焦点所在。建议删除全局 outline 抑制，或为各控件补充清晰可见的 :focus 样式（如 primary 按钮改用 box-shadow/内描边）。

**现有代码**

```python
    outline: none;
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 438. `app/ui/theme.py:85` · 中 / 缺陷

> primary 按钮没有按下反馈：`QPushButton:pressed` 与 `QPushButton[variant="primary"]` 的 CSS2 特异性相同（属性选择器与伪类同权重），而后者在样式表中位置更靠后，会覆盖按下的 `background: surface_alt`，导致 primary 按钮按下时背景仍是 primary。建议为 primary 变体显式补一条 :pressed 规则。

**现有代码**

```python
QPushButton:pressed {{ background: {p.surface_alt}; }}
```

**改进建议**

```python
QPushButton:pressed {{ background: {p.surface_alt}; }}
QPushButton[variant="primary"]:pressed {{ background: {p.primary_hover}; }}
```

#### 439. `app/ui/theme.py:91` · 中 / 缺陷

> 禁用态 primary 按钮文字几乎不可读：该规则只覆盖了 background，`color` 仍取自已声明的 `QPushButton:disabled { color: {p.text_faint} }`（#aab2c3），叠在 #a9bdf5 上对比度约 1.1:1。仓库中 interpreters_page 的 load_button 就是 primary 且初始被 setEnabled(False)，用户会看到一个“空白”按钮。建议为禁用态 primary 指定深色文字或改用浅色底。

**现有代码**

```python
QPushButton[variant="primary"]:disabled {{ background: #a9bdf5; }}
```

**改进建议**

```python
QPushButton[variant="primary"]:disabled {{ background: {p.primary_soft}; color: {p.text_muted}; }}
```

#### 440. `app/ui/theme.py:217` · 低 / 可维护性

> 字体族在 QSS 的 `*` 规则和 `app.setFont` 中重复定义且回退链不一致（QSS 缺少 SimHei）。由于 QSS 优先级高于 QWidget 字体，`setFamilies` 的字体族实际上对所有控件都不生效（只有字号 9.5 生效）；同时后续调整字体需要改两处，容易漂移。建议抽出一个模块级常量（如 FONT_FAMILIES），QSS 与 QFont 共用，保证回退链一致。

**现有代码**

```python
    font.setFamilies(["Segoe UI", "Microsoft YaHei UI", "SimHei", "PingFang SC"])
```

**改进建议**

```python
    font.setFamilies(FONT_FAMILIES)
```

#### 441. `app/ui/theme.py:159` · 低 / 可维护性

> 滚动条 handle 的 #c9d1e0 与 Palette.border_strong 完全同值，#aeb9cf、#e4e9f4、#2b3245、#a9bdf5 等也属主题色却硬编码在 QSS 中。当色板调整时这些位置会被漏改，造成主题不一致。建议把滚动条/悬浮/提示气泡等颜色也收敛到 Palette（如 border_strong、新增 scrollbar_hover、tooltip_bg 等）。

**现有代码**

```python
    background: #c9d1e0; border-radius: 5px; min-height: 36px;
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 442. `app/ui/theme.py:57` · 低 / 可维护性

> 未知 variant 被静默回退为 muted 色，调用方拼写错误（如 "warning" 代替 "warn"）会得到“看似正常但语义错误”的颜色，很难排查。widgets.py 中的状态徽章依赖此函数，建议对未注册的 variant 至少记录一条 warning 日志（或在开发期断言），便于及早暴露。

**现有代码**

```python
    pair = STATUS_COLORS.get(variant, STATUS_COLORS["muted"])
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 443. `app/ui/theme.py:61-62` · 低 / 可维护性

> `qcolor` 只是 `QColor` 的空包装，且全仓库无任何引用（其余模块都直接 `QColor(...)`），属于无用公开 API/死代码，建议删除以免误导调用方。

**现有代码**

```python
def qcolor(hexstr: str) -> QColor:
    return QColor(hexstr)
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 444. `app/core/conda_scanner.py:440` · 中 / 缺陷

> 自研解析器不支持 flow 风格集合（YAML 中完全合法且常见，如 `channels: [defaults, conda-forge]`、`envs_dirs: ['/opt/conda/envs']`）。这类值会走 `_scalar` 分支被当作普通字符串，`CondaConfigFile.channels/envs_dirs` 对非 list 值返回空列表，于是自定义频道与 `envs_dirs` 被静默丢弃——`.condarc` 里声明的额外环境目录将完全扫描不到，且没有任何 error 提示，用户很难察觉。建议在标量分支前识别 `[...]` 形式并拆分为列表（同时至少在解析器 docstring 中显式声明该限制）。

**现有代码**

```python
            result[key] = _scalar(val)
```

**改进建议**

```python
            if val.startswith("[") and val.endswith("]"):
                inner = val[1:-1].strip()
                result[key] = [_scalar(x) for x in inner.split(",")] if inner else []
            else:
                result[key] = _scalar(val)
```

#### 445. `app/core/conda_scanner.py:390-391` · 低 / 缺陷

> 文档分隔符的判定放在 `_strip_inline_comment` 之前，导致 `--- # 头部说明` 这类带行内注释的合法分隔行无法被识别，随后会被 `_parse_map` 当成键名 `---`（或 `... # xxx`）写入结果，污染 `top_keys`。建议先剥离行内注释再做分隔符判断。

**现有代码**

```python
        if stripped in ("---", "..."):  # 文档分隔符
            continue
```

**改进建议**

```python
        # 先剥注释再判断分隔符，避免 `--- # note` 被当成键
        # （顺序调整见下方 stripped = _strip_inline_comment(stripped)）
```

#### 446. `app/core/conda_scanner.py:51` · 低 / 缺陷

> docstring 承诺“永不抛异常”，但函数体的大部分调用都不在任何 try 内：`find_conda_roots()`（跨模块，依赖环境变量/注册表探测）、`_condarc_paths()`/`os.path.expanduser`、以及 `_norm()` 里的 `os.path.realpath/os.path.abspath` 只捕获了 `OSError`，遇到 `ValueError`（如来自 `.condarc` 的非法路径含 NUL）或其它意外异常时会直接向上冒泡，后台扫描线程整体失败、UI 拿不到任何结果。建议在 `scan_conda` 外层加一层 `except Exception` 兜底并写入 `info.errors`，使契约成立。

**现有代码**

```python
    """执行完整的 conda 扫描(永不抛异常, 错误进 errors 列表)。"""
```

**改进建议**

```python
    """执行完整的 conda 扫描(永不抛异常, 错误进 errors 列表)。

    实现上以 try/except Exception 包裹主体，异常记入 info.errors 后返回。
    """
```

#### 447. `app/ui/manage_page.py:454` · 严重 / 缺陷

> `_start_op` 的形参名是 `result_text`,这里(以及 `_remove_python`、`_create_conda_env`、`_remove_conda_env` 共 4 处)都传了不存在的关键字 `result=`,调用时直接抛 `TypeError: _start_op() got an unexpected keyword argument 'result'`。由于异常发生在 `_set_busy(True, title)` 之后、`self._worker` 赋值之前,界面会永久停在“正在执行”状态且所有按钮保持禁用,安装/删除功能完全不可用。请统一改为 `result_text=`。

**现有代码**

```python
            result=f"安装目录: {os.path.join(em.get_runtimes_dir(), 'py-' + version)}")
```

**改进建议**

```python
            result_text=f"安装目录: {os.path.join(em.get_runtimes_dir(), 'py-' + version)}")
```

#### 448. `app/ui/manage_page.py:555-556` · 严重 / 缺陷

> pip 分支把 index（镜像标签字符串）作为第 3 个位置参数传给 fn，但 pip_uninstall(python_exe, package, on_output=None) 的第 3 个参数是 on_output，卸载会因 multiple values for 'on_output' 或 'str' object is not callable 失败。请按 op 分别传参：仅 pip_install 追加镜像参数，pip_uninstall 不要传 index；修正示例时不要加 return，否则会跳过 conda 分支。

**现有代码**

```python
            fn = em.pip_install if op == "pip_install" else em.pip_uninstall
            self._start_op(title, fn, target, spec, index,
```

**改进建议**

```python
            if op == "pip_install":
                self._start_op(title, em.pip_install, target, spec, index,
                               after=f"packages:{target}",
                               message=f"{op_names[op]} 操作已完成: {spec}",
                               result_text=f"目标: {target}")
            else:
                self._start_op(title, em.pip_uninstall, target, spec,
                               after=f"packages:{target}",
                               message=f"{op_names[op]} 操作已完成: {spec}",
                               result_text=f"目标: {target}")
            return
            # 以下为原 conda 分支参数(保持不变)
```

#### 449. `app/ui/manage_page.py:500-501` · 高 / 缺陷

> 创建/删除 conda 环境时都直接使用 self._conda_info.executable，其为 None 时传给 conda 命令会 TypeError/FileNotFoundError；创建分支还计算了从未使用的 conda_exe，且 POSIX 回退会拼成 root/Scripts/bin/conda。建议抽出 _conda_executable() 统一做根目录回退，并供创建、删除两处复用。

**现有代码**

```python
        conda_exe = self._conda_info.executable or os.path.join(
            root, "Scripts", "conda.exe" if os.name == "nt" else "bin", "conda")
```

**改进建议**

```python
        conda_exe = self._conda_info.executable or (
            os.path.join(root, "Scripts", "conda.exe") if os.name == "nt"
            else os.path.join(root, "bin", "conda"))
```

#### 450. `app/ui/manage_page.py:598` · 中 / 缺陷

> `output` 信号只被保存为属性,页面从未把它连接到 `_log_line`,也没有任何其他接收者。这与文件头部“输出实时写入底部日志面板”的承诺不符:pip/conda 安装的长耗时过程中用户看不到任何进度,只有开始/结束两行。建议在 `__init__` 或包装器内连接:`self.output.connect(page._log_line)`(`page` 已在构造时持有)。

**现有代码**

```python
        self.output = self._qthread.output
```

**改进建议**

```python
        self.output = self._qthread.output
        self.output.connect(page._log_line)
```

#### 451. `app/ui/manage_page.py:460` · 中 / 缺陷

> 用表格行号去索引“重新读取”的磁盘列表并不可靠:表格填充后若托管解释器集合发生变化(手工删除目录、多实例操作或 `_set_busy(False)` 期间的重扫),`row` 会指向错误条目而删错目录,列表变短时还会抛 IndexError。建议在 `_reload_py_table` 时把 `item["dir"]` 写入 `Qt.UserRole`,删除时从当前行读取该值,而不是按索引回查。

**现有代码**

```python
        item = em.list_managed_interpreters()[row]
```

**改进建议**

```python
        item = {"dir": self.py_table.item(row, 1).data(Qt.UserRole),
                "version": self.py_table.item(row, 0).text().replace("Python ", "")}
```

#### 452. `app/ui/manage_page.py:599` · 中 / 缺陷

> `_ManageWorkerWrapper` 不是 QObject,`_on_done` 是普通 Python 对象上的绑定方法。`ManageWorker`(QThread)在 `run()`(工作线程)中 `emit(done)`,对非 QObject 接收者 Qt 无法依据接收者线程亲和性排队,存在在工作线程内直接调用 `page._on_op_success()` 的风险,而该槽会重载表格(`setRowCount`/`setItem`)并弹出 `QMessageBox`,属于跨线程操作 UI。建议让包装器继承 `QObject`(parent=page)或显式使用 `Qt.ConnectionType.QueuedConnection`;同时 `_on_op_success/_on_op_failed` 里立即 `self._worker = None` 时线程尚未从 `run()` 返回,紧接着启动新操作会出现两个线程并发执行环境操作,建议在 `finished` 信号里再清理。

**现有代码**

```python
        self._qthread.done.connect(self._on_done)
```

**改进建议**

```python
        self._qthread.done.connect(self._on_done, Qt.ConnectionType.QueuedConnection)
```

#### 453. `app/ui/manage_page.py:339` · 低 / 可维护性

> 该表达式实际等价于 `has_conda and w is not self.env_remove_btn`(末尾的 `or False` 是冗余的),因此循环中 `env_remove_btn` 恒被禁用,随后又由 `_update_env_remove_enabled()` 重新启用,逻辑绕且易误读;紧接其后的三行 `setEnabled(has_conda)` 也与循环重复。建议只保留一次显式赋值,把“是否可删”统一交给 `_update_env_remove_enabled()`。

**现有代码**

```python
            w.setEnabled(has_conda and w is not self.env_remove_btn or False)
```

**改进建议**

```python
            w.setEnabled(has_conda)
```

#### 454. `app/ui/manage_page.py:18` · 低 / 可维护性

> `QSplitter`(本行)与 `make_badge`(下方 `from .widgets import ...`)在本文件中从未使用,属于死导入,建议删除以免误导后续维护者。

**现有代码**

```python
    QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTableWidget,
```

**改进建议**

```python
    QMessageBox, QPlainTextEdit, QPushButton, QTableWidget,
```

#### 455. `main.py:14-16` · 中 / 可维护性

> main.py 两处 try 都把内部模块导入失败与 PySide6/packaging 缺失混为一谈：app.ui.theme 或 app.main_window 缺失时 err.name 可能是 app/app.ui，却仍提示 pip install PySide6 packaging；第二处还未打印 traceback。建议分开捕获内部模块与第三方依赖，输出异常详情/traceback，并区分提示文案。

**现有代码**

```python
    try:
        from PySide6.QtWidgets import QApplication
        from app.ui.theme import apply_theme
```

**改进建议**

```python
    try:
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError as err:
        print(f"缺少依赖模块 {err.name}, 请先执行:  pip install PySide6 packaging")
        return 1

    try:
        from app.ui.theme import apply_theme
    except ModuleNotFoundError as err:
        print(f"无法导入内部模块 {err.name}: {err}")
        return 1
```

#### 456. `app/workers.py:12` · 低 / 可维护性

> `ScanReport` 只出现在下方 `done = Signal(object)  # ScanReport` 的注释里，代码中并未引用，属于无用导入，建议删除以保持导入表干净。

**现有代码**

```python
from .core.scanner import ScanReport, scan_interpreters
```

**改进建议**

```python
from .core.scanner import scan_interpreters
```

#### 457. `app/workers.py:34-35` · 低 / 可维护性

> 失败语义与其它 Worker 不一致：`ScanWorker` / `CollectWorker` / `LayoutWorker` / `ManageWorker` 在异常时都发 `failed`，而 `CondaScanWorker` 把异常塞进 `CondaInfo.errors` 后仍然发 `done`，且没有暴露 `failed` 信号。调用方（main_window._on_conda_done）必须额外检查 `info.errors` 才能发现扫描失败，容易在后续改动中漏掉错误处理。建议统一为「部分错误放 errors、整体失败发 failed」，或至少补一个 `failed` 信号并保留原堆栈信息。

**现有代码**

```python
    progress = Signal(str)
    done = Signal(object)  # CondaInfo
```

**改进建议**

```python
    progress = Signal(str)
    done = Signal(object)  # CondaInfo
    failed = Signal(str)
```

#### 458. `app/workers.py:53-55` · 中 / 缺陷

> `ManageWorker` 承载的是 pip/conda 安装、卸载这类可能运行数分钟甚至 1 小时（env_manager 中 timeout=3600）的子进程任务，但这里没有任何取消/中断接口。上层 `MainWindow.closeEvent` 在 `wait(3000)` 超时后会直接 `terminate()` 线程，被强杀的线程无法回收 Popen 子进程，可能残留子进程并把目标环境留在半安装状态。建议提供协作式取消（如 `request_cancel()` + `threading.Event`，由 on_output 回调检查并中断子进程），并在文档中说明禁止对运行中的 ManageWorker 调用 terminate。

**现有代码**

```python
    output = Signal(str)
    done = Signal(object)
    failed = Signal(str)
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 459. `app/ui/graph_view.py:148-151` · 严重 / 缺陷

> `DeleteWhenStopped` 会在动画结束(自然结束或显式 stop)后销毁 C++ 对象, 而 `self._scale_anim` 仍持有该包装器。第一次悬停缩放动画跑完后再次悬停, 第 138 行 `self._scale_anim.stop()` 会抛 `RuntimeError: Internal C++ object already deleted`(PySide6 经典悬挂引用问题); 悬停离开时同样会崩。建议不要用 `DeleteWhenStopped`, 让动画作为 NodeItem 的子对象常驻复用, 由下一次动画 `stop()`+重设参数重启。

**现有代码**

```python
        anim.valueChanged.connect(self.apply_scale)
        anim.finished.connect(lambda: self.apply_scale(target))
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        self._scale_anim = anim
```

**改进建议**

```python
        anim.valueChanged.connect(self.apply_scale)
        anim.finished.connect(lambda: self.apply_scale(target))
        # 不使用 DeleteWhenStopped: 销毁 C++ 对象后 self._scale_anim 会变成
        # 悬垂引用, 下一次 stop() 直接抛 RuntimeError
        anim.start()
        self._scale_anim = anim
```

#### 460. `app/ui/graph_view.py:665-667` · 高 / 缺陷

> `clear()` 没有停止上一次 build 创建的 `_EntranceAnimator`。重建图时旧动画仍以 controller 为父对象持续运行: 它会继续改写已被 `removeItem` 的旧节点/边(并通过 `_nodes/_edges` 引用导致这些元素无法释放), 且其 `_finish` 会把新图的 `_animating` 置回 False 并触发 `on_build_finished` → `fit_to_view`, 在新入场动画(节点还是 0.55 缩放)期间按错误几何做适配。建议给 `_EntranceAnimator` 增加 `stop()`(停止 `_anim` 并断开 finished), 在 `__init__` 中初始化 `self._entrance = None`, 并在 clear 中停止并置空。

**现有代码**

```python
    def clear(self) -> None:
        self._flow_timer.stop()
        self._flow_edges = []
```

**改进建议**

```python
    def clear(self) -> None:
        self._flow_timer.stop()
        self._flow_edges = []
        if getattr(self, "_entrance", None) is not None:
            self._entrance.stop()       # 需为 _EntranceAnimator 新增 stop()
            self._entrance = None       # 释放对旧节点/边的引用
```

#### 461. `app/ui/graph_view.py:849-850` · 中 / 缺陷

> 防抖定时器在触发前不再检查用户是否已接管视图。若 200ms 内用户滚轮缩放或按下鼠标(`_user_zoomed=True`), 待触发的 `fit_to_view` 仍会重置视角, 把用户刚做的缩放覆盖掉。建议 timeout 连到一个带守卫的槽, 并在 `wheelEvent`/`mousePressEvent` 中 `self._resize_fit_timer.stop()`。

**现有代码**

```python
            timer.setInterval(200)
            timer.timeout.connect(self.fit_to_view)
```

**改进建议**

```python
            timer.setInterval(200)
            timer.timeout.connect(self._on_resize_fit_timeout)   # 槽内先判断 _user_zoomed 再 fit
```

#### 462. `app/ui/graph_view.py:710-711` · 中 / 性能

> 这里直接覆盖 `_opacity_anim`, 未停止上一轮可能仍在运行的渐变动画: 两套动画会同时写同一批 item 的 opacity(目标互相覆盖造成闪烁), 且旧 animator 以 controller 为父对象、`_stop()` 里只清 controller 引用而不销毁自身, 反复悬停/聚焦会让 controller 的子对象与 `_items`(引用历史图的节点/边)无限累积, 同时拖住已 removeItem 的元素。建议新建前先 `stop()` 旧实例, 并在 `_OpacityAnimator._stop()` 末尾调用 `self.deleteLater()`。

**现有代码**

```python
        if node_anim or edge_anim:
            self._opacity_anim = _OpacityAnimator(self, node_anim, edge_anim)
```

**改进建议**

```python
        if node_anim or edge_anim:
            if self._opacity_anim is not None:
                self._opacity_anim.stop()   # 先停旧动画, 避免两套目标互相覆盖
            self._opacity_anim = _OpacityAnimator(self, node_anim, edge_anim)
```

#### 463. `app/ui/graph_view.py:395-401` · 中 / 性能

> `paint()` 是流动边的 30fps 热路径(`advance_flow` 每帧 `update()`), 而这里每帧都用 `elementAt()` 重新拼一条 `QPainterPath`, 箭头路径也每帧重建; FLOW_EDGE_LIMIT=120 时约每秒 240 次路径构造, 与文件本身的性能优化目标相悖。建议在 `update_path()` 中一次性构建并缓存 `_curve_path` / `_arrow_path`, paint 只读取缓存。

**现有代码**

```python
        curve = QPainterPath()
        if path.elementCount() >= 3:
            el0 = path.elementAt(0)
            curve.moveTo(el0.x, el0.y)
            el1 = path.elementAt(1)
            el2 = path.elementAt(2)
            curve.quadTo(el1.x, el1.y, el2.x, el2.y)
```

**改进建议**

```python
        # 曲线路径在 update_path() 中构建并缓存, paint 只读, 避免每帧重建
        curve = self._curve_path
```

#### 464. `app/ui/graph_view.py:445` · 低 / 缺陷

> 标签框宽度按 `QFontMetrics.horizontalAdvance(label)` 计算且以路径 45% 处为中心, 但 boundingRect 只固定外扩 90px。当 spec 较长(如 `>=1.0.0,<2.0.0,!=1.5.3`, 宽度可超 180px)时, 标签会画到几何范围之外, 造成残影/刷新不完整。建议按实际文本宽度缓存半宽(在 `set_highlight`/文本变化时用 QFontMetrics 算一次), boundingRect 取 `max(90, half_width + 6)`。

**现有代码**

```python
        return super().boundingRect().adjusted(-90, -30, 90, 14)
```

**改进建议**

```python
        half = max(90.0, self._label_half_width + 6.0)
        return super().boundingRect().adjusted(-half, -30, half, 14)
```

#### 465. `app/ui/graph_view.py:777` · 低 / 性能

> `chain_edges` 是 list, 此处对每条边做 `in` 判断是 O(n), 整体 O(n²); 在包含数千条边的图上聚焦一条冲突边会明显卡顿。建议在调用前构造 `chain_edge_ids = {id(e) for e in chain_edges}`, 改为按 id 判断(同函数内 `chain_nodes` 已用 set)。

**现有代码**

```python
            {id(e): (1.0 if e in chain_edges else 0.10) for e in self.edges},
```

**改进建议**

```python
            {id(e): (1.0 if id(e) in chain_edge_ids else 0.10) for e in self.edges},
```

#### 466. `app/ui/graph_view.py:65` · 低 / 可维护性

> `_base_pos` 及配套的 `base_pos` 属性在全仓库中只有赋值/定义, 没有任何读取点(入场动画直接使用 `setPos` 的当前位置), 注释“动画使用”具有误导性, 属于死状态。建议删除该字段与属性, 或让入场动画真正从 `_base_pos` 起算以实现位移入场。

**现有代码**

```python
        self._base_pos = QPointF(0.0, 0.0)   # 布局目标位置(动画使用)
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 467. `scripts/make_icon.py:34-35` · 中 / 可维护性

> `for _ in range(1): pass` 是永远只执行一次且无任何副作用的空循环，属于死代码，还会让读者误以为这块逻辑有特殊处理。直接删除即可。

**现有代码**

```python
        for _ in range(1):
            pass
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 468. `scripts/make_icon.py:79` · 中 / 缺陷

> `os.path.dirname(out_path)` 在传入不带目录的路径（例如 `build_icon("pyenv.ico")`，该函数是公开入口，`scripts/build_msi.py` 已在复用）时返回空串，`os.makedirs("", exist_ok=True)` 会抛 `FileNotFoundError`。建议先判空再创建目录。

**现有代码**

```python
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
```

**改进建议**

```python
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
```

#### 469. `scripts/make_icon.py:58` · 低 / 缺陷

> 候选字体全部为 Windows 路径，非 Windows 环境会落到 `ImageFont.load_default()`：1) 在 Pillow < 10.1 中该函数忽略字号，返回的是位图字体，“Py” 会非常小且下方 bar 布局失配；2) 其返回类型是 `ImageFont.ImageFont` 而非注解声明的 `FreeTypeFont`。建议至少传入 size（新版 Pillow 支持），并在无法加载时给出明确日志/异常，避免静默生成畸形图标。

**现有代码**

```python
    return ImageFont.load_default()
```

**改进建议**

```python
    # 非 Windows:退回默认字体;Pillow>=10.1 支持 size 参数,避免文字过小
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        print("WARN: no bold font found, fallback to tiny default font")
        return ImageFont.load_default()
```

#### 470. `scripts/make_icon.py:11` · 低 / 可维护性

> 脚本后续只 `from PIL import ...`，没有导入任何仓库内模块，这个 `sys.path` 插入没有任何作用（`sys` 也因此只在此处使用）。建议删除这两行及 `import sys`，减少对运行时路径的副作用。

**现有代码**

```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 471. `app/ui/packages_page.py:8` · 低 / 可维护性

> `QPen` 在本文件中没有任何引用(圆点与文字绘制只用了 setPen(QColor)/Qt.NoPen),属于未使用的导入,建议移除。

**现有代码**

```python
from PySide6.QtGui import QColor, QFont, QPainter, QPen
```

**改进建议**

```python
from PySide6.QtGui import QColor, QFont, QPainter
```

#### 472. `app/ui/packages_page.py:292-298` · 中 / 缺陷

> 清空详情时只重置了状态徽章的文本,没有把 `variant` 属性复位并重新 polish。之前选中冲突(missing/warn)包后,若筛选导致无选中项(例如搜索无结果触发 currentRowChanged 传入无效索引),徽章会残留上一次的红色/黄色样式与“—”文本不匹配。建议同时把 variant 设回 muted 并刷新样式。

**现有代码**

```python
        if pkg is None:
            self._name.setText("—")
            self._version_badge.setText("—")
            self._status_badge.setText("—")
            self._out_title.setText("依赖 (0)")
            self._in_title.setText("被依赖 (0)")
            return
```

**改进建议**

```python
        if pkg is None:
            self._name.setText("—")
            self._version_badge.setText("—")
            self._status_badge.setText("—")
            self._status_badge.setProperty("variant", "muted")
            self._status_badge.style().unpolish(self._status_badge)
            self._status_badge.style().polish(self._status_badge)
            self._out_title.setText("依赖 (0)")
            self._in_title.setText("被依赖 (0)")
            return
```

#### 473. `app/ui/packages_page.py:287-289` · 中 / 缺陷

> 仅调用 `deleteLater()` 时,控件在返回事件循环前仍是 content 的子控件并保持原几何位置,而新的一批 `_EdgeRow` 已加入布局,可能出现旧行与新行短暂重叠/闪烁(切换包时尤其明显)。建议先 `setParent(None)` 立即从界面摘除,再 deleteLater 释放。

**现有代码**

```python
                w = item.widget()
                if w is not None:
                    w.deleteLater()
```

**改进建议**

```python
                w = item.widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()
```

#### 474. `app/ui/packages_page.py:426-428` · 中 / 性能

> `clicked` 与 `currentRowChanged` 在正常点击换行时会同时触发,导致 `show_package` 连续执行两次:每次都要清空并重建全部依赖/被依赖 `_EdgeRow` 控件(大包可达上百条),属于重复的控件创建与布局开销,也放大了上面的闪烁问题。`currentRowChanged` 已覆盖点击切行的场景(重复点击同一行时详情内容本就一致),建议只保留一个入口,或在 `_on_row_clicked` 中按 `pkg.key` 去重。

**现有代码**

```python
        self.table.clicked.connect(self._on_row_clicked)
        self.table.selectionModel().currentRowChanged.connect(
            self._on_current_row_changed)
```

**改进建议**

```python
        self.table.selectionModel().currentRowChanged.connect(
            self._on_current_row_changed)
```

#### 475. `app/ui/widgets.py:88` · 高 / 缺陷

> `_do_layout` 返回的高度少算了顶部 contentsMargin。`effective.y()` 已经是 `rect.y() + margins.top()`,用它去减会把上边距抵消掉,于是 `heightForWidth()` 只返回「内容高度 + 下边距」,缺少上边距;容器按此高度布局时最后一行会被裁切(当 `heightForWidth` 传入 `QRect(0,0,width,0)` 时尤为明显)。官方 FlowLayout 示例中使用的是 `rect.y()`。

**现有代码**

```python
        return y + line_height - effective.y() + margins.bottom()
```

**改进建议**

```python
        return y + line_height - rect.y() + margins.bottom()
```

#### 476. `app/ui/widgets.py:265-266` · 中 / 缺陷

> `draw_py_icon` 直接修改传入的 `QPainter` 的 Antialiasing、画笔、字体和状态,却既不 `save()` 也不 `restore()`,调用方在调用后继续绘制会沿用白色画笔与 "Py" 字体,产生难以定位的渲染异常。建议在函数入口 `painter.save()`,结束处 `painter.restore()`(或使用局部的 QPainter 副本)。

**现有代码**

```python
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
```

**改进建议**

```python
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
```

#### 477. `app/ui/widgets.py:8` · 低 / 可维护性

> `QSizePolicy` 导入后在整个文件中未被使用,属于无用的导入,建议移除以保持导入整洁。

**现有代码**

```python
    QFrame, QHBoxLayout, QLabel, QLayout, QLineEdit, QSizePolicy, QVBoxLayout,
```

**改进建议**

```python
    QFrame, QHBoxLayout, QLabel, QLayout, QLineEdit, QVBoxLayout,
```

#### 478. `app/ui/widgets.py:110` · 低 / 可维护性

> `self._variant` 只在 `__init__` 中赋值,之后再无任何读取处,属于冗余字段(色条已通过 `status_color(variant)` 一次性取色)。建议删除该字段,或在需要动态切换配色时补一个读取它的 `set_variant` 方法。

**现有代码**

```python
        self._variant = variant
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 479. `app/ui/widgets.py:232-234` · 低 / 可维护性

> `self._text` 在 `start()`/`set_text()` 中被反复赋值,但自 `__init__` 里构造 `QLabel(self._text)` 之后就没有任何地方读取它(标签文本直接取自参数),属于无效状态。建议删掉该字段,只保留 `self._label.setText(...)`。

**现有代码**

```python
    def set_text(self, text: str) -> None:
        self._text = text
        self._label.setText(text)
```

**改进建议**

```python
    def set_text(self, text: str) -> None:
        self._label.setText(text)
```

#### 480. `scripts/ui_screenshot.py:49-53` · 中 / 缺陷

> 超时分支直接 return 1，但此时扫描线程仍在运行；main() 返回后局部变量 win 被回收，QMainWindow 析构会连带销毁仍在 running 的 QThread，Qt 内部走 qFatal("QThread: Destroyed while thread is still running") 直接 abort，最终退出码/输出不是预期的 1。另外这里的同步 wait 在唯一的 GUI 线程里阻塞事件循环（最长 20s，下面 conda 分支 30s），期间窗口不重绘、queued 信号不投递。建议超时分支先 quit()/terminate() 并 wait(2000) 清理线程后再返回，conda 分支做同样处理。

**现有代码**

```python
    if win._scan_worker is not None:
        if not win._scan_worker.wait(QDeadlineTimer(20000)):
            print("SCAN_TIMEOUT: 扫描线程 20s 内未结束, 截图不可信",
                  file=sys.stderr)
            return 1
```

**改进建议**

```python
    if win._scan_worker is not None:
        if not win._scan_worker.wait(QDeadlineTimer(20000)):
            print("SCAN_TIMEOUT: 扫描线程 20s 内未结束, 截图不可信",
                  file=sys.stderr)
            win._scan_worker.quit()
            if not win._scan_worker.wait(2000):
                win._scan_worker.terminate()
                win._scan_worker.wait(1000)
            return 1
```

#### 481. `scripts/ui_screenshot.py:99-100` · 低 / 缺陷

> 冲突表为空说明演示数据/分析结果异常（或分析尚未完成），但这里只打印跳过，后续仍会继续抓图并最终输出 SCREENSHOTS_OK 并返回 0；同时 OUT_DIR 未清理，上一轮遗留的 shot_5_focus.png 会被当作本次验证产物，造成“验证通过”的假象。建议把该情况按失败处理（返回非 0），或在脚本开头清理输出目录中本脚本生成的旧截图。

**现有代码**

```python
        print("SCREENSHOT_SKIPPED: 冲突表为空, 跳过 shot_5_focus.png",
              file=sys.stderr)
```

**改进建议**

```python
        print("SCREENSHOT_FAILED: 冲突表为空, 无法验证聚焦截图",
              file=sys.stderr)
        return 1
```

#### 482. `scripts/ui_screenshot.py:44-46` · 中 / 可维护性

> 用 QThread.msleep 在 GUI 线程里“等待”只是把界面冻结，动画/布局只能在这 9 次 processEvents 的瞬间推进；settle(1700) 等待入场动画、settle(400) 等待聚焦渐变这类固定毫秒数在慢机器或负载高时仍可能截到中间帧，导致截图验证结果不稳定。建议改为用 QEventLoop + QTimer 驱动等待，或直接等待动画 finished 状态 / 监听布局与 worker 信号，用条件而不是魔法延时来同步。

**现有代码**

```python
        for _ in range(8):
            app.processEvents()
            QThread.msleep(max(ms // 8, 10))
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 483. `scripts/ui_screenshot.py:79` · 低 / 可维护性

> 脚本直接依赖 MainWindow 的私有成员（_load_demo、_goto_page、_scan_worker、_conda_worker、analysis_page._on_conflict_clicked），并硬编码页面号 3/4/1/2 与 Tab 号 1/2/3。MainWindow 已提供公开的 load_demo()，应优先使用；页面顺序或 Tab 顺序一旦调整，脚本会静默截错页面却仍打印 SCREENSHOTS_OK。建议改用公开入口，并把页面/Tab 索引抽成具名常量或由被测窗口暴露。

**现有代码**

```python
    win._load_demo()
```

**改进建议**

```python
    win.load_demo()
```

#### 484. `scripts/build_msi.py:48-49` · 高 / 缺陷

> RTF 的 `\uN` 是**有符号 16 位**值，码点大于 32767 时必须写成负数（N-65536）。当前许可文本里就有多个超限汉字（如「软」U+8F6F=36719、「适」U+9002=36866、「须」U+987B=39035、「装」U+88C5=35013、「议」U+8BAE=35758），生成 `\u36719?` 这类非法控制字会让 MSI 许可页显示乱码或落回 `?`。另外非 BMP 字符（>0xFFFF）需要拆成代理对。

**现有代码**

```python
        if code > 127:
            out.append(f"\\u{code}?")
```

**改进建议**

```python
        if code > 0xFFFF:
            # 非 BMP 字符需拆成代理对
            cp = code - 0x10000
            out.append(f"\\u{0xD800 + (cp >> 10)}?")
            out.append(f"\\u{0xDC00 + (cp & 0x3FF)}?")
        elif code > 127:
            # RTF 的 \uN 为有符号 16 位, 大于 32767 需写成负数
            out.append(f"\\u{code - 0x10000 if code > 32767 else code}?")
```

#### 485. `scripts/build_msi.py:99-100` · 中 / 缺陷

> 版本号校验过宽：`isdigit()` 对全角/其它 Unicode 数字（如 `１.２.３`、`١.٢.٣`）也返回 True，且未限制必须为 3 段、未检查取值范围。该值随后直接写入 WiX `$(var.Version)` 和产物文件名，`1.2.3.4` 或 `999.0.0` 会导致 candle/light 报错或生成非法 MSI（MSI 前两段上限 255、第三段上限 65535）。

**现有代码**

```python
    if not all(part.isdigit() for part in version.split(".")):
        sys.exit(f"[错误] 版本号格式应为 a.b.c, 收到: {version!r}")
```

**改进建议**

```python
    parts = version.split(".")
    if len(parts) != 3 or not all(p.isascii() and p.isdigit() for p in parts):
        sys.exit(f"[错误] 版本号格式应为 a.b.c (ASCII 数字), 收到: {version!r}")
    if int(parts[0]) > 255 or int(parts[1]) > 255 or int(parts[2]) > 65535:
        sys.exit(f"[错误] 版本号超出 MSI 允许范围(a.b<=255, c<=65535), 收到: {version!r}")
```

#### 486. `scripts/build_msi.py:134` · 中 / 缺陷

> `heat -gg` 会在每次构建时为相同文件重新生成随机组件 GUID，组件标识在不同构建之间不稳定：后续做小版本升级/补丁（minor upgrade、patch）或修复安装时无法匹配旧组件，容易造成文件残留或重复安装。建议改用 `-ag`（编译期按文件路径生成稳定 GUID）。

**现有代码**

```python
        "-gg",          # 自动生成组件 GUID
```

**改进建议**

```python
        "-ag",          # 编译期按文件路径生成稳定 GUID
```

#### 487. `scripts/build_msi.py:18` · 低 / 可维护性

> `shutil` 在文件中没有被引用，属于无用导入，建议删除。

**现有代码**

```python
import shutil
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 488. `scripts/build_msi.py:64` · 低 / 可维护性

> 该 `replace("\n\n", "")` 永远不会生效：`_rtf_escape` 已把 `\n` 转成 `\par\n`，结果里不会再出现连续的 `\n\n`；`split("\n\n")` 也保证每段不含空行。若原文出现三连换行，段落会以残留的 `\n` 开头并被拼成 `\par\line\n\par\n`，产生多余空行。建议先对空白做归一化（如 `p.strip().replace("\n", " ")`）再转义。

**现有代码**

```python
        _rtf_escape(p).replace("\n\n", "") for p in _LICENSE_TEXT.split("\n\n")
```

**改进建议**

```python
        _rtf_escape(p.strip().replace("\n", " "))
        for p in _LICENSE_TEXT.split("\n\n")
```

#### 489. `tools/wix314/sdk/Microsoft.Deployment.Compression.xml:781-782` · 中 / 文档

> 两处示例标题与正文互串：c-0 的 PACKING EXAMPLE 实际描述解压（extracting a simple archive file...），应改为 UNPACKING/EXTRACTING EXAMPLE；c-1 的 UNPACKING EXAMPLE 实际描述打包（Packing 3 files...），应改为 PACKING EXAMPLE，并顺带去掉冒号后的重复空格。

**现有代码**

```xml
            <p>PACKING EXAMPLE: The following sequence of events might be received when
            extracting a simple archive file with 2 files.</p>
```

**改进建议**

```xml
            <p>UNPACKING EXAMPLE: The following sequence of events might be received when
            extracting a simple archive file with 2 files.</p>
```

#### 490. `tools/wix314/sdk/Microsoft.Deployment.Compression.xml:79-80` · 低 / 文档

> 序列化构造函数与 GetObjectData 的文档存在复制粘贴错误：ArchiveFileInfo、ArchiveInfo、ZipFileInfo、CabFileInfo 的 SerializationInfo 参数被描述为 about the exception being thrown，应改为对应文件或归档对象数据；ZipFileInfo.GetObjectData 与 CabFileInfo.GetObjectData 的 summary 又把对象写成 archive，应改为 file。另请核对 CabFileInfo 写入与读取所用的 SerializationInfo 键名是否严格对应，避免跨版本反序列化丢失文件属性、长度等字段。

**现有代码**

```xml
            <param name="info">The SerializationInfo that holds the serialized
            object data about the exception being thrown.</param>
```

**改进建议**

```xml
            <param name="info">The SerializationInfo that holds the serialized
            object data about the archive file.</param>
```

#### 491. `tools/wix314/sdk/Microsoft.Deployment.Compression.xml:957` · 低 / 可维护性

> 文档引用了非公开成员 `archiveFiles`（私有字段）。该 cref 在生成文档时无法解析为公开 API，读者也无从跳转，属于失效链接；建议改为引用公开属性 `P:Microsoft.Deployment.Compression.ArchiveFileStreamContext.ArchiveFiles`，与技术备注中其它位置（GetArchiveName / OpenArchiveWriteStream 的 remarks）保持一致。

**现有代码**

```xml
            <see cref="F:Microsoft.Deployment.Compression.ArchiveFileStreamContext.archiveFiles"/> list with the specified index, or an empty
```

**改进建议**

```xml
            <see cref="P:Microsoft.Deployment.Compression.ArchiveFileStreamContext.ArchiveFiles"/> list with the specified index, or an empty
```

#### 492. `tools/wix314/sdk/Microsoft.Deployment.Compression.xml:1210-1214` · 低 / 文档

> Finalize 的摘要写成“Disposes the compression engine”，但它只是终结器（由 GC 调用），与公开的 `Dispose()` 语义不同：它不应释放托管资源、不保证在特定线程执行，调用方也无法直接调用。建议明确说明这是终结器并说明其仅处理非托管资源，否则易诱导调用方手工调用 Finalize 或误判资源释放时机。

**现有代码**

```xml
        <member name="M:Microsoft.Deployment.Compression.CompressionEngine.Finalize">
            <summary>
            Disposes the compression engine.
            </summary>
        </member>
```

**改进建议**

```xml
        <member name="M:Microsoft.Deployment.Compression.CompressionEngine.Finalize">
            <summary>
            Finalizer that releases unmanaged resources held by the compression engine.
            Managed resources are released by <see cref="M:Microsoft.Deployment.Compression.CompressionEngine.Dispose"/>.
            </summary>
        </member>
```

#### 493. `tools/wix314/sdk/Microsoft.Deployment.Compression.xml:357-358` · 中 / 文档

> 摘要描述了签名中不存在的行为：`Unpack(string, EventHandler<ArchiveProgressEventArgs>)` 并没有“仅解压较新文件”的参数，唯一的开关是 `ArchiveFileStreamContext.ExtractOnlyNewerFiles`。这类“文档声称有、签名里没有”的描述会让调用方误以为可以通过该重载控制覆盖策略（尤其在默认覆盖已有文件的语义下，误判后果是数据被覆盖）。建议删除该表述或改为指向 ExtractOnlyNewerFiles。

**现有代码**

```xml
            Extracts all files from an archive to a destination directory,
            optionally extracting only newer files.
```

**改进建议**

```xml
            Extracts all files from an archive to a destination directory.
            Whether existing newer files are overwritten depends on
            <see cref="P:Microsoft.Deployment.Compression.ArchiveFileStreamContext.ExtractOnlyNewerFiles"/>.
```

#### 494. `tools/wix314/sdk/Microsoft.Deployment.Compression.xml:1400-1401` · 低 / 风格

> 公开 API 文档中存在多处拼写错误，会直接出现在调用方的 IDE 提示/在线文档里：Compresion→Compression（DosDateAndTimeToDateTime 与 DateTimeToDosDateAndTime 两处）、sublcasses→subclasses（OnProgress）、compromize→compromise（CompressionLevel.Normal）、relevent→relevant（ArchiveException）、Case-senstivity→case-sensitivity（UnpackFileSet）、archiv→archive（PartialArchive）、to pack all files（语法不通）。建议批量修正。

**现有代码**

```xml
            Compresion utility function for converting old-style
            date and time values to a DateTime structure.
```

**改进建议**

```xml
            Compression utility function for converting old-style
            date and time values to a DateTime structure.
```

#### 495. `tools/wix314/sdk/Microsoft.Deployment.Compression.Zip.xml:482` · 中 / 文档

> ZipInfo 的两个构造函数文档均从 CabinetInfo 复制而来：普通构造函数写成 Creates a new CabinetInfo object...，序列化构造函数写成 Initializes a new instance of the CabinetInfo class...，均应改为 ZipInfo，避免 IntelliSense 使用者误以为是 Cabinet 相关类型。

**现有代码**

```xml
            Creates a new CabinetInfo object representing a zip file in a specified path.
```

**改进建议**

```xml
            Creates a new ZipInfo object representing a zip file in a specified path.
```

#### 496. `tools/wix314/sdk/Microsoft.Deployment.Compression.Zip.xml:63` · 中 / 文档

> CrcStream.Seek 的 remarks 已声明“跳过的字节不计入 CRC”，但 Position 的 setter 同样会改变底层流位置（本质是 seek），却完全没有相同提示。上层若用 Position 定位后再做流式读写，会得到与文件实际内容不匹配的 CRC，导致 ZIP 校验失败或写入错误 CRC。建议在此处补充与 Seek 一致的说明（setter 不累加 CRC）。

**现有代码**

```xml
            Gets or sets the position of the source stream.
```

**改进建议**

```xml
            Gets or sets the position of the source stream.
            </summary>
            <remarks>
            Setting the position is equivalent to calling <see cref="M:Microsoft.Deployment.Compression.Zip.CrcStream.Seek(System.Int64,System.IO.SeekOrigin)"/>;
            bytes skipped over are not included in the CRC.
            </remarks>
```

#### 497. `tools/wix314/sdk/Microsoft.Deployment.Compression.Zip.xml:261` · 中 / 文档

> RegisterCompressionStreamCreator 修改的是进程级静态注册表，影响所有 ZipEngine 实例，文档却未说明并发注册/注销的线程安全性，也未说明重复注册是覆盖还是追加、creator 返回 null 或注册失败时的行为。多线程压缩/解压场景极易出现不确定行为，建议至少补充“静态全局状态、重复注册覆盖已注册项、需在并发使用前完成注册”。同时此处 "ether" 为 "either" 的拼写错误。

**现有代码**

```xml
            <param name="compressionMode">Indicates registration for ether
```

**改进建议**

```xml
            <param name="compressionMode">Indicates registration for either
```

#### 498. `tools/wix314/sdk/Microsoft.Deployment.Compression.Zip.xml:197` · 中 / 文档

> ZipCompressionMethod 列出了 Shrink/Reduce*/Implode/Deflate64/BZip2/Lzma/Ppmd 等多种算法，但文档未说明解包时的失败契约：当遇到未通过 RegisterCompressionStreamCreator 注册的方法时，是抛 ArchiveException 还是跳过该条目。这是解包正确性与错误处理的关键契约缺失，建议在此类型说明或各方法说明中明确“未注册/不支持的压缩方法在解包时抛出 ArchiveException”。

**现有代码**

```xml
            The file is compressed using the BZIP2 algorithm.
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 499. `tools/wix314/sdk/Microsoft.Deployment.Compression.Zip.xml:311` · 中 / 文档

> IsArchive 的语义（必须“无偏移”才返回 true）与 FindArchiveOffset（支持 0 或更多字节偏移，且要求 4 字节对齐）不一致且未交叉引用。自解压（SFX）归档或带前缀数据的流会被 IsArchive 判为 false，调用方据此短路就会跳过本可解析的归档。建议在 IsArchive 注释中说明其等价于 FindArchiveOffset(...) == 0，并指引带偏移场景改用 FindArchiveOffset。

**现有代码**

```xml
            (with no offset); false otherwise.</returns>
```

**改进建议**

```xml
            (with no offset); false otherwise. To detect an archive that may
            be preceded by other data (such as a self-extracting stub),
            use <see cref="M:Microsoft.Deployment.Compression.Zip.ZipEngine.FindArchiveOffset(System.IO.Stream)"/> instead.</returns>
```

#### 500. `tools/wix314/sdk/Microsoft.Deployment.Compression.Zip.xml:356` · 中 / 文档

> 参数类型是 IEnumerable<string>（一次调用对应一个归档中的文件路径枚举），但文档写成“An array of file lists. Each list is compressed into one stream”，与签名不符，容易让调用方误以为需要传入“文件列表的数组/嵌套集合”。建议改为描述单次调用只打包一个归档，超限时由 maxArchiveSize 触发归档链。

**现有代码**

```xml
            <param name="files">An array of file lists.  Each list is
```

**改进建议**

```xml
            <param name="files">An enumerable of file paths.  All files in the list are
```

#### 501. `tools/wix314/sdk/Microsoft.Deployment.Compression.Zip.xml:415` · 中 / 文档

> 注释只说“checking the crc at the end”，未说明 CRC 不匹配时的具体契约：抛出哪种异常（ArchiveException/ZipException 及内部错误码）、已写出的部分目标文件是否被清理/保留、以及已消耗的源归档流是否能继续处理后续条目。这正是解包失败后易产生“半成品文件”与归档链错位的场景，建议补全。

**现有代码**

```xml
            checking the crc at the end.
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 502. `tools/wix314/sdk/Microsoft.Deployment.Compression.Zip.xml:125` · 低 / 文档

> 该公开方法只有摘要，缺少 buffer/offset/count 的 <param> 说明（同文件内 Read/Write 都有完整参数文档），也未说明 count 越界时的异常。相邻的 MakeCrcTable（缺少 <returns>）与 Reflect（缺少 offset/length 参数与返回值说明）同样文档不完整，建议补齐以保持 API 契约一致。

**现有代码**

```xml
            Updates the CRC with a range of bytes that were read or written.
```

**改进建议**

```xml
            Updates the CRC with a range of bytes that were read or written.
            </summary>
            <param name="buffer">The buffer containing the bytes to include in the CRC.</param>
            <param name="offset">The zero-based byte offset in buffer at which to begin.</param>
            <param name="count">The number of bytes to include in the CRC.</param>
```

#### 503. `tools/wix314/sdk/Microsoft.Deployment.Compression.Zip.xml:10` · 低 / 风格

> 拼写错误集中出现在多处 doc 注释中，会直接显示在 IDE 的 IntelliSense 提示里："steream"→"stream"、"calcaluates"→"calculates"、"warpper"→"wrapper"、"exmample"→"example"（另见 RegisterCompressionStreamCreator 的 "ether"）。建议统一修正，避免对外发布文档中出现明显错字。

**现有代码**

```xml
            a series of (chunked) streams instead of a single steream.
```

**改进建议**

```xml
            a series of (chunked) streams instead of a single stream.
```

#### 504. `tools/wix314/sdk/Microsoft.Deployment.Compression.Cab.xml:383` · 高 / 文档

> FCI 句柄的 ReleaseHandle 文档被写成了“调用 FDIDestroy()”，而 FCI 句柄对应的销毁函数是 FCIDestroy()（FDIDestroy 属于 FDI 引擎）。这段显然是从下方 FDI.Handle 段落复制而来。该文档是 SDK 对外契约，若实现也照此调用，会造成 FCI/FDI 句柄类型错配、资源泄漏甚至原生端崩溃，请改为 FCIDestroy() 并确认实现一致。

**现有代码**

```xml
            Releases the handle by calling FDIDestroy().
```

**改进建议**

```xml
            Releases the handle by calling FCIDestroy().
```

#### 505. `tools/wix314/sdk/Microsoft.Deployment.Compression.Cab.xml:372-373` · 低 / 文档

> 拼写错误：`unintialized` 应为 `uninitialized`。此处以及 Fargo 下方 `Microsoft.Deployment.Compression.Cab.NativeMethods.FDI.Handle.#ctor`（同样一句）各出现一次，建议一并修正，避免生成的 SDK 文档出现相同错字。

**现有代码**

```xml
            Creates a new unintialized handle. The handle will be initialized
            when it is marshalled back from native code.
```

**改进建议**

```xml
            Creates a new uninitialized handle. The handle will be initialized
            when it is marshalled back from native code.
```

#### 506. `tools/wix314/sdk/Microsoft.Deployment.Compression.Cab.xml:456` · 低 / 文档

> ERF.Error 是对外可见的属性，但文档只描述了内部实现技巧（用 int 代替 bool 以适配 GCHandle），没有说明属性语义（是否表示“发生过错误/错误是否有效”），调用方无法据此正确使用。建议补充语义说明，把实现细节移到 remark 中。

**现有代码**

```xml
            GCHandle doesn't like the bool type, so use an int underneath.
```

**改进建议**

```xml
            Gets or sets a value indicating whether an error occurred.
            </summary>
            <remarks>GCHandle doesn't like the bool type, so use an int underneath.</remarks>
```

#### 507. `tools/wix314/sdk/Microsoft.Deployment.Compression.Cab.xml:464` · 中 / 可维护性

> 本文件以及 Microsoft.Deployment.WindowsInstaller.Linq.xml 等 tools/wix314/sdk 下的 XML 文档都混入了 Microsoft.Tools.WindowsInstallerXml.WixDistribution 成员文档；该类型属于 WiX 工具链，不在对应程序集内。建议在生成或合并 XML 文档的脚本中过滤掉该片段，而非只改单个文件。

**现有代码**

```xml
        <member name="T:Microsoft.Tools.WindowsInstallerXml.WixDistribution">
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 508. `tools/wix314/sdk/BootstrapperCore.xml:367-369` · 中 / 文档

> 文档拷贝粘贴错误：`OnDetectForwardCompatibleBundle` 的 summary 写成了 "Called when the update detection phase has begun."，与其对应的事件 `DetectForwardCompatibleBundle`（“Fired when a forward compatible bundle is detected.”）语义不符。开发者据此会误以为该方法在更新检测阶段被调用，从而把前向兼容 bundle 的判断逻辑放进错误的生命周期里。建议改为对应的前向兼容语义，并与事件文档保持一致。

**现有代码**

```xml
        <member name="M:Microsoft.Tools.WindowsInstallerXml.Bootstrapper.BootstrapperApplication.OnDetectForwardCompatibleBundle(Microsoft.Tools.WindowsInstallerXml.Bootstrapper.DetectForwardCompatibleBundleEventArgs)">
            <summary>
            Called when the update detection phase has begun.
```

**改进建议**

```xml
        <member name="M:Microsoft.Tools.WindowsInstallerXml.Bootstrapper.BootstrapperApplication.OnDetectForwardCompatibleBundle(Microsoft.Tools.WindowsInstallerXml.Bootstrapper.DetectForwardCompatibleBundleEventArgs)">
            <summary>
            Called when a forward compatible bundle is detected.
```

#### 509. `tools/wix314/sdk/BootstrapperCore.xml:212-213` · 中 / 文档

> 无效的 cref：`M:Engine.SetLocalSource` / `M:Engine.SetDownloadSource` 缺少完整命名空间与参数签名，编译期会产生 CS1574 之类的 XML 注释警告，生成的 IntelliSense 中该链接也无法跳转。注意同样的两行在 `OnResolveSource` 的 summary 中又出现了一次（第 ~610 行附近），需两处一并修正为 `M:Microsoft.Tools.WindowsInstallerXml.Bootstrapper.Engine.SetLocalSource(System.String,System.String,System.String)` 与对应的 `SetDownloadSource` 重载。

**现有代码**

```xml
            Fired by the engine to allow the user experience to change the source
            using <see cref="M:Engine.SetLocalSource"/> or <see cref="M:Engine.SetDownloadSource"/>.
```

**改进建议**

```xml
            Fired by the engine to allow the user experience to change the source
            using <see cref="M:Microsoft.Tools.WindowsInstallerXml.Bootstrapper.Engine.SetLocalSource(System.String,System.String,System.String)"/> or <see cref="M:Microsoft.Tools.WindowsInstallerXml.Bootstrapper.Engine.SetDownloadSource(System.String,System.String,System.String,System.String,System.String)"/>.
```

#### 510. `tools/wix314/sdk/BootstrapperCore.xml:1137-1139` · 中 / 文档

> 同一批事件参数构造函数文档均引用了错误的 Args 类型（复制粘贴残留）：DetectForwardCompatibleBundleEventArgs ctor 误写 DetectUpdateBeginEventArgs；DetectUpdateEventArgs ctor 也误写 DetectUpdateBeginEventArgs；DetectTargetMsiPackageEventArgs ctor 误写 DetectMsiFeatureEventArgs；PlanTargetMsiPackageEventArgs ctor 误写 PlanMsiFeatureEventArgs；CacheAcquireProgressEventArgs 与 CacheAcquireCompleteEventArgs ctor 均误写 CacheAcquireBeginEventArgs。请分别改为自身类型。

**现有代码**

```xml
            Creates a new instance of the <see cref="T:Microsoft.Tools.WindowsInstallerXml.Bootstrapper.DetectUpdateBeginEventArgs"/> class.
            </summary>
            <param name="bundleId">The identity of the forward compatible bundle.</param>
```

**改进建议**

```xml
            Creates a new instance of the <see cref="T:Microsoft.Tools.WindowsInstallerXml.Bootstrapper.DetectForwardCompatibleBundleEventArgs"/> class.
            </summary>
            <param name="bundleId">The identity of the forward compatible bundle.</param>
```

#### 511. `tools/wix314/sdk/BootstrapperCore.xml:2692` · 低 / 文档

> XML 注释使用了错误属性名 `type`，`<exception>` 标签只支持 `cref`，因此该异常说明不会在 IntelliSense/生成的文档中关联到 `System.ComponentModel.Win32Exception`（同时会触发 CS1570 之类警告）。建议改为 `cref`。

**现有代码**

```xml
            <exception type="Win32Exception">The command line could not be parsed into an array.</exception>
```

**改进建议**

```xml
            <exception cref="T:System.ComponentModel.Win32Exception">The command line could not be parsed into an array.</exception>
```

#### 512. `tools/wix314/sdk/BootstrapperCore.xml:922-923` · 中 / 安全

> 凭据相关 API 缺少安全约定说明：`SetDownloadSource` 的 `password` 参数以及 `SecureStringVariables`、`Engine.Log` 都没有任何“不得明文记录/记录到日志或异常信息”的提示。安装日志与错误上报是常见泄露面，建议在此处补充 `<remarks>`，明确密码仅可用于代理认证、不得写入日志、也不应通过 `Log`/`LogLevel.Verbose` 输出，并说明优先使用 `SecureStringVariables` 传递敏感变量。

**现有代码**

```xml
            <param name="user">The user name for proxy authentication.</param>
            <param name="password">The password for proxy authentication.</param>
```

**改进建议**

```xml
            <param name="user">The user name for proxy authentication.</param>
            <param name="password">The password for proxy authentication.</param>
            <remarks>
            <para>The password is used only for proxy authentication. It must never be written to the log
            (including <see cref="M:Microsoft.Tools.WindowsInstallerXml.Bootstrapper.Engine.Log(Microsoft.Tools.WindowsInstallerXml.Bootstrapper.LogLevel,System.String)"/>) or included in error messages.</para>
            <para>Use <see cref="P:Microsoft.Tools.WindowsInstallerXml.Bootstrapper.Engine.SecureStringVariables"/> for sensitive variables.</para>
            </remarks>
```

#### 513. `tools/wix314/sdk/BootstrapperCore.xml:2445-2449` · 低 / 文档

> 公开枚举只有类型级 summary，没有任何成员（字段）说明，例如 `Display`、`Result`、`PackageState`、`RequestState`、`FeatureState`、`FeatureAction`、`RelationType`、`ActionState`、`LaunchAction`、`InstallMessage`、`Restart` 等。`Result`/`RequestState`/`ActionState` 直接决定传给引擎或从引擎返回的取值，缺少成员说明会让调用方无法确认每个枚举值对应的引擎行为（例如 Result.Ok / Cancel / Error 分别如何处理）。建议至少为会跨引擎边界传递的枚举补齐 `<member name="F:...">` 文档。

**现有代码**

```xml
        <member name="T:Microsoft.Tools.WindowsInstallerXml.Bootstrapper.Display">
            <summary>
            The display level for the UX.
            </summary>
        </member>
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 514. `tools/wix314/sdk/BootstrapperCore.xml:318` · 低 / 文档

> `Command` / `Engine` 属性的 cref 指向了属性自身（`P:...BootstrapperApplication.Command`），而不是被返回的类型，注释语义变成“获取 Command 的信息”，无法跳转到 `T:...Command`/`T:...Engine` 类型。建议改为类型 cref，便于使用者查看返回类型定义（`Engine` 属性同样存在此问题）。

**现有代码**

```xml
            Gets the <see cref="P:Microsoft.Tools.WindowsInstallerXml.Bootstrapper.BootstrapperApplication.Command"/> information for how the UX should be started.
```

**改进建议**

```xml
            Gets the <see cref="T:Microsoft.Tools.WindowsInstallerXml.Bootstrapper.Command"/> information for how the UX should be started.
```

#### 515. `tools/wix314/sdk/BootstrapperCore.xml:1183-1186` · 低 / 文档

> `DetectUpdateBeginEventArgs.UpdateLocation` 的 summary 写成“Gets the identity of the bundle to detect.”，与属性名/构造函数参数（location to check for an updated bundle）语义不符，容易让使用者把 URL/路径当作 bundleId 使用。建议改为描述位置。

**现有代码**

```xml
        <member name="P:Microsoft.Tools.WindowsInstallerXml.Bootstrapper.DetectUpdateBeginEventArgs.UpdateLocation">
            <summary>
            Gets the identity of the bundle to detect.
            </summary>
```

**改进建议**

```xml
        <member name="P:Microsoft.Tools.WindowsInstallerXml.Bootstrapper.DetectUpdateBeginEventArgs.UpdateLocation">
            <summary>
            Gets the location to check for an updated bundle.
            </summary>
```

#### 516. `tools/wix314/sdk/BootstrapperCore.xml:966` · 低 / 可维护性

> 此处文档化的 `containsVariable` / `getStringVariable` / `convertToSecureString` 均为 lowerCamelCase 命名，与同一类型中公开成员 `Variables<T>.Contains` 不一致，且 `getStringVariable` 返回的是需要调用方 `Marshal.FreeCoTaskMem` 释放的裸 `IntPtr`。如果这些成员是内部实现细节，建议从公开文档中移除（`<exclude/>` 或改为 private/internal）；如必须公开，请补充 `<returns>` 与失败路径（返回空指针时是否还允许调用 FreeCoTaskMem）的说明，避免调用方误用导致内存泄漏或重复释放。

**现有代码**

```xml
        <member name="M:Microsoft.Tools.WindowsInstallerXml.Bootstrapper.Engine.containsVariable(System.String)">
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 517. `tools/wix314/sdk/BootstrapperCore.xml:2118` · 低 / 文档

> 拼写错误：“clas” 应为 “class”，且同段 `ApplyCompleteEventArgs` 相关文档中还存在 “then engine”、“visilibity”、“complets”、“exteded”、“arugments” 等多处拼写问题，建议统一校对以保证生成的 API 文档质量。

**现有代码**

```xml
            Creates a new instance of the <see cref="T:Microsoft.Tools.WindowsInstallerXml.Bootstrapper.ApplyCompleteEventArgs"/> clas.
```

**改进建议**

```xml
            Creates a new instance of the <see cref="T:Microsoft.Tools.WindowsInstallerXml.Bootstrapper.ApplyCompleteEventArgs"/> class.
```

#### 518. `tools/wix314/sdk/Microsoft.Deployment.WindowsInstaller.Package.xml:116` · 中 / 文档

> cref 目标错误：`System.Colletions` 拼写错误（应为 `Collections`），且返回值是接口类型却用了 `M:` 前缀并使用了非法的 `` `1{string,string} `` 写法。XML 文档生成时会报 CS1574（无效 cref）或至少生成失效链接，读者也无法跳转到 `IDictionary<string,string>`。同时摘要中写的是 “Binary files”，与这里泛化的 “files” 描述不一致，容易让调用方误以为只能取 Binary 表文件。

**现有代码**

```xml
            <returns>A <see cref="M:System.Colletions.Generic.IDictionary`1{string,string}"/> of the filename/fullpath key value pairs of the directory given.</returns>
```

**改进建议**

```xml
            <returns>A <see cref="T:System.Collections.Generic.IDictionary{TKey,TValue}"/> of the filename/fullpath key value pairs found in the given directory.</returns>
```

#### 519. `tools/wix314/sdk/Microsoft.Deployment.WindowsInstaller.Package.xml:135` · 中 / 文档

> 两个 UpdateFiles 重载对同一行为的描述不一致：无参重载写 `MsiFileHash.HashPart*`，带 fileKeys 的重载写 `MsiFileHash.HashPart?`。“?”是明显的排版残字，且两者实际更新字段应为同一集合（HashPart1~HashPart4）。公开 API 文档描述不一致会让调用方对“更新后哪些列会变化”产生歧义，请统一为准确表述（若某些情况下确实不写 Hash 表，应显式说明条件）。

**现有代码**

```xml
            following data: File.FileSize, File.Version, File.Language, MsiFileHash.HashPart?.
```

**改进建议**

```xml
            following data: File.FileSize, File.Version, File.Language, and MsiFileHash.HashPart1 through HashPart4
            (the MsiFileHash row is only updated when the file is unversioned).
```

#### 520. `tools/wix314/sdk/Microsoft.Deployment.WindowsInstaller.Package.xml:207-210` · 高 / 文档

> CompressionLevel 属性的 remarks 与属性语义完全无关，是从 Directories/Files 属性复制过来的：压缩级别并不涉及 Directory 表映射，也不存在“关闭重开包才生效”的 mapping 缓存问题。该错误说明会误导调用方对压缩级别生效时机的理解（例如误以为必须重开包才生效）。请改为说明压缩级别的取值范围/默认值及其对 UpdateFiles、Consolidate 的影响。

**现有代码**

```xml
            <remarks>
            If the Directory table is modified, this mapping will be outdated
            until you close and reopen the install package.
            </remarks>
```

**改进建议**

```xml
            <remarks>
            The compression level is applied the next time files are re-cabbed; it does
            not retroactively affect cabinets that were already built.
            </remarks>
```

#### 521. `tools/wix314/sdk/Microsoft.Deployment.WindowsInstaller.Package.xml:416` · 中 / 文档

> `targetRootDir` 的参数说明写成了“所有**源**路径的根目录”，与它真实语义（目标路径的根目录）相反，且与紧邻的 `sourceRootDir` 说明重复。调用方按此文档配置会把源目录当成目标根目录传入，导致 BuildDirectoryPathMap 生成的 TargetPaths 错误。

**现有代码**

```xml
            <param name="targetRootDir">The root directory path of all source paths, or null to leave them relative.</param>
```

**改进建议**

```xml
            <param name="targetRootDir">The root directory path of all target paths, or null to leave them relative.</param>
```

#### 522. `tools/wix314/sdk/Microsoft.Deployment.WindowsInstaller.Package.xml:551` · 中 / 文档

> 此处说明与同一类型的 PatchCode 属性文档自相矛盾：PatchCode 明确写“patch code 存于 RevisionNumber 字段”，而本方法又说“被替换的补丁码存于 RevisionNumber 字段”，两者不可能同时成立。按 MSI 补丁摘要信息的约定，被替换的补丁码（分号分隔）位于 Comments 字段。请核对实现后更正，否则调用方会按错误的摘要字段去解析 MSP。

**现有代码**

```xml
            The list of replaced patch codes is stored in the RevisionNumber field of the patch summary information.
```

**改进建议**

```xml
            The list of replaced patch codes is stored in the Comments field of the patch summary information.
```

#### 523. `tools/wix314/sdk/Microsoft.Deployment.WindowsInstaller.Package.xml:150` · 低 / 文档

> `mediaCabinet` 参数没有任何说明，属于必填/可选信息缺失：调用方无法从文档判断传入 null、空字符串或外部 cabinet 名称分别是什么行为（内嵌 cabinet vs 外部 cabinet vs 沿用原 Media 表）。请补充参数语义。

**现有代码**

```xml
            <param name="mediaCabinet"></param>
```

**改进建议**

```xml
            <param name="mediaCabinet">Name of the cabinet to use for the consolidated files, or null
            to keep the existing media cabinet name.</param>
```

#### 524. `tools/wix314/sdk/Microsoft.Deployment.WindowsInstaller.Package.xml:275` · 低 / 风格

> 多处拼写/笔误影响文档质量：`a a directory`（InstallPath.ChildPaths）、`direcotry`（InstallPathMap.Item/Add/ContainsKey 共 3 处）。这些公开 API 文档会随 SDK 一起发布，建议统一修正为 `a directory`、`directory`。

**现有代码**

```xml
            Gets the set of child paths if this InstallPath object represents a a directory.
```

**改进建议**

```xml
            Gets the set of child paths if this InstallPath object represents a directory.
```

#### 525. `tools/wix314/sdk/Microsoft.Deployment.WindowsInstaller.Linq.xml:98-99` · 中 / 文档

> 第二个构造参数 `outputPath` 的语义是“输出数据库文件路径”，但描述写成了 “Open mode for the database”，与同文件其它构造函数中 `mode` 参数的描述完全重复，调用方很容易按开库模式（DatabaseOpenMode 枚举）来传值而在运行期抛异常。另外构造函数不能有返回值，`<returns>` 标签在 ctor 上是无效文档（编译后不会出现在 IntelliSense 中，且与 `<summary>/<param>` 语义冲突）。

**现有代码**

```xml
            <param name="outputPath">Open mode for the database</param>
            <returns>Database object representing the created or opened database</returns>
```

**改进建议**

```xml
            <param name="outputPath">Path of the output database file to be created from the original database.</param>
```

#### 526. `tools/wix314/sdk/Microsoft.Deployment.WindowsInstaller.Linq.xml:154` · 低 / 文档

> 拼写错误：“datbaase” 应为 “database”。同时该索引器缺少 `<returns>` 说明（返回的是 QTable 查询对象，且同样受 `DatabaseTableAttribute` 表名推断规则影响），建议补充。

**现有代码**

```xml
            Gets a queryable table from the datbaase.
```

**改进建议**

```xml
            Gets a queryable table from the database.
```

#### 527. `tools/wix314/sdk/Microsoft.Deployment.WindowsInstaller.Linq.xml:277-280` · 中 / 文档

> 列名重载的 Update 允许任意列名字符串直接拼进 MSI SQL 并写库，但文档既没有说明“列名必须存在于表 schema 中、非法列名会抛 InstallerException”，也没有像索引重载那样声明“主键字段不可更新，需 Delete+Insert”。这属于数据完整性与错误处理契约缺失（调用方可能在不知情的情况下改主键或拼出非法 SQL）。建议补充 `<exception>` 与 `<remarks>`。

**现有代码**

```xml
        <member name="M:Microsoft.Deployment.WindowsInstaller.Linq.QRecord.Update(System.Collections.Generic.IList{System.String},System.Collections.Generic.IList{System.String})">
            <summary>
            Update multiple fields in the record (and the database).
            </summary>
```

**改进建议**

```xml
        <member name="M:Microsoft.Deployment.WindowsInstaller.Linq.QRecord.Update(System.Collections.Generic.IList{System.String},System.Collections.Generic.IList{System.String})">
            <summary>
            Update multiple fields in the record (and the database).
            </summary>
            <param name="fields">column names of fields to update; each name must exist in the table schema</param>
            <param name="values">new values for each field being updated; must have the same count as fields</param>
            <exception cref="T:Microsoft.Deployment.WindowsInstaller.InstallerException">a column name is invalid or the update fails</exception>
            <remarks>
            The record (primary keys) must already exist in the table.
            <para>Updating primary key fields is not yet implemented; use Delete() and Insert() instead.</para>
            </remarks>
```

#### 528. `tools/wix314/sdk/Microsoft.Deployment.WindowsInstaller.Linq.xml:325-327` · 中 / 文档

> 所有“Not yet implemented”的成员（Refresh/Assign/Merge/Validate/ValidateNew/ValidateFields/ValidateDelete）都只写了这句话，没有说明实际行为：是抛 NotImplementedException/NotSupportedException，还是静默无操作？调用方无法据此编写异常处理（例如 QRecord.Update 是否会隐式调用 Validate）。建议统一补充异常契约或明确标注为 no-op。

**现有代码**

```xml
        <member name="M:Microsoft.Deployment.WindowsInstaller.Linq.QRecord.Refresh">
            <summary>
            Not yet implemented.
```

**改进建议**

```xml
        <member name="M:Microsoft.Deployment.WindowsInstaller.Linq.QRecord.Refresh">
            <summary>
            Not yet implemented.
            </summary>
            <exception cref="T:System.NotImplementedException">always thrown; this member is reserved for future use</exception>
```

#### 529. `tools/wix314/sdk/Microsoft.Deployment.WindowsInstaller.Linq.xml:221-223` · 中 / 文档

> 公共无参构造函数文档承认“直接调用会导致 NullReferenceException”，但没有对应的 `<exception>` 声明；而且用一个未初始化的对象状态换取 `new()` 约束，属于不良 API 设计——后期任何访问都会在任意位置抛出 NRE，难以定位。建议至少显式声明异常，并考虑改为抛 InvalidOperationException 并附带可诊断的错误信息（如“use QTable.NewRecord()”）。

**现有代码**

```xml
        <member name="M:Microsoft.Deployment.WindowsInstaller.Linq.QRecord.#ctor">
            <summary>
            Do not call. Use QTable.NewRecord() instead.
```

**改进建议**

```xml
        <member name="M:Microsoft.Deployment.WindowsInstaller.Linq.QRecord.#ctor">
            <summary>
            Do not call. Use QTable.NewRecord() instead.
            </summary>
            <exception cref="T:System.InvalidOperationException">thrown when methods are called on an instance created directly by this constructor (not associated with a table)</exception>
```

#### 530. `tools/wix314/sdk/Microsoft.Deployment.WindowsInstaller.Linq.xml:303` · 低 / 文档

> 拼写错误：“Prmary keys” 应为 “Primary keys”，该错误在 `QRecord.Insert` 与 `QRecord.Insert(System.Boolean)` 两处重复出现，会被原样展示在 IntelliSense 中。

**现有代码**

```xml
            record. Prmary keys and all required fields
```

**改进建议**

```xml
            record. Primary keys and all required fields
```

#### 531. `tools/wix314/sdk/Microsoft.Deployment.WindowsInstaller.Linq.xml:60` · 低 / 文档

> `AsQueryable` 的 `db` 参数没有任何描述；而 remarks 中“两个实例共用一个 MSI 句柄，只关闭其中一个即可”的所有权约定非常关键（否则会出现双重关闭或句柄泄漏），却未说明应该关闭哪一个、AsQueryable 返回的实例是否 ownsHandle。建议明确写出所有权归属。

**现有代码**

```xml
            <param name="db"></param>
```

**改进建议**

```xml
            <param name="db">database instance to convert; must not be null</param>
```

#### 532. `tools/wix314/sdk/Microsoft.Deployment.WindowsInstaller.Linq.xml:408-412` · 低 / 文档

> `<returns></returns>` 为空，未说明枚举返回的元素类型（TRecord 实例，且每次枚举都会重新执行 MSI SQL 查询、不缓存结果）。建议补充返回值与惰性求值/资源释放相关的说明。

**现有代码**

```xml
        <member name="M:Microsoft.Deployment.WindowsInstaller.Linq.QTable`1.GetEnumerator">
            <summary>
            Enumerates over all records in the table.
            </summary>
            <returns></returns>
```

**改进建议**

```xml
        <member name="M:Microsoft.Deployment.WindowsInstaller.Linq.QTable`1.GetEnumerator">
            <summary>
            Enumerates over all records in the table.
            </summary>
            <returns>An enumerator over the records (TRecord instances) in the table; the underlying query is re-executed on each enumeration.</returns>
```

#### 533. `tools/wix314/sdk/Microsoft.Deployment.Resources.xml:12` · 高 / 文档

> BitmapResource 的 remarks 把位图资源标注为 RT_GROUPICON（图标组资源），与其自身语义不符，正确应为 RT_BITMAP。文档是调用方判断资源类型的唯一依据，错误的常量会让使用者把位图资源当作图标组处理（例如错误地按 GRPICONDIR 解析）。另建议核对 ResourceType.Bitmap 成员的实际种类（静态字段还是属性），确保 cref 的 P:/F: 前缀与程序集一致，否则文档链接会失效。

**现有代码**

```xml
            The resource is of type <see cref="P:Microsoft.Deployment.Resources.ResourceType.Bitmap"/> (RT_GROUPICON).
```

**改进建议**

```xml
            The resource is of type <see cref="P:Microsoft.Deployment.Resources.ResourceType.Bitmap"/> (RT_BITMAP).
```

#### 534. `tools/wix314/sdk/Microsoft.Deployment.Resources.xml:183` · 中 / 文档

> ResourceCollection 的 remarks 中 Load/Save 条目文字声称是 Resource 类的方法，但 cref 却指向 ResourceCollection.Load/Save；应改为 M:Microsoft.Deployment.Resources.Resource.Load(System.String) 与 M:Microsoft.Deployment.Resources.Resource.Save(System.String)。另外 Find 的第三个参数实际是资源 name，摘要却写成 given type and language，应按参数说明改为按 name 搜索。

**现有代码**

```xml
            Locates all resources in a file of a given type and language.  For each located resource,
```

**改进建议**

```xml
            Locates all resources in a file of a given type and name.  For each located resource,
```

#### 535. `tools/wix314/sdk/Microsoft.Deployment.Resources.xml:132` · 中 / 文档

> Equals/GetHashCode 的相等性完全基于 ResourceType、Name、Locale 三个可写属性（三者均有 setter），而文档没有任何提示。一旦把 Resource（或可变的 ResourceType）作为 Dictionary/HashSet 的键后再修改这些属性，哈希值变化会导致查找、去重和集合运算静默失效。建议在 Equals 或类级 <remarks> 中明确说明“作为字典键后不可修改 type/name/locale”，并注明 null/非 Resource 入参返回 false。

**现有代码**

```xml
            Tests if type, name, and locale of this Resource object match another Resource object.
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 536. `tools/wix314/sdk/Microsoft.Deployment.Resources.xml:205` · 低 / 文档

> 索引器只给了摘要，缺少 <param name="index"> 与 <value> 说明，也未标注越界时抛出的异常（如 ArgumentOutOfRangeException）。ResourceCollection.Item 是读写入口，边界行为（负索引、>= Count）对调用方很关键，建议补齐异常契约。

**现有代码**

```xml
            Gets or sets the element at the specified index.
```

**改进建议**

```xml
            Gets or sets the element at the specified index.
            </summary>
            <param name="index">The zero-based index of the element to get or set.</param>
            <value>The <see cref="T:Microsoft.Deployment.Resources.Resource"/> at the specified index.</value>
            <exception cref="T:System.ArgumentOutOfRangeException">index is less than 0 or greater than or equal to <see cref="P:Microsoft.Deployment.Resources.ResourceCollection.Count"/>.</exception>
            <summary>
```

#### 537. `tools/wix314/sdk/Microsoft.Deployment.Resources.xml:273-274` · 低 / 文档

> 文档仅描述 “以 # 前缀表示整数资源类型”，但未说明解析边界：空字符串/null 是否抛 ArgumentNullException、"#abc" 或 "#-1"/超出 ushort 范围的值是否抛 FormatException/溢出，以及带 # 但转不成数字时是否退化为自定义字符串类型。ResourceType 是资源定位的关键标识，这些规则缺失会导致调用方在异常处理和类型一致性上做出错误假设。建议在 <exception> 中补充。

**现有代码**

```xml
            <param name="resourceType">String resource name,
            or an integer resource type prefixed by a #.</param>
```

**改进建议**

按上述问题描述调整实现（工具未给出具体替换代码）。

#### 538. `tools/wix314/sdk/Microsoft.Deployment.Resources.xml:61` · 低 / 文档

> 描述不准确：Win32 常量名为 RT_GROUP_ICON（带下划线），当前文本 RT_GROUPICON 并非合法标识符；且 RT_GROUP_ICON 是资源类型，不是数据结构，GroupIconResource.Data 的实际内存布局应为 GRPICONDIR / GRPICONDIRENTRY 头部。同文件第 41 行也同样误写为 RT_GROUPICON。建议修正为 “RT_GROUP_ICON resource type ... GRPICONDIR structure”，以便调用方按正确的结构体解析原始字节。

**现有代码**

```xml
            Gets or sets the raw data of the resource.  The data is in the format of the RT_GROUPICON resource structure.
```

**改进建议**

```xml
            Gets or sets the raw data of the resource.  The data is in the format of the GRPICONDIR resource structure (RT_GROUP_ICON).
```

> 会话 ID `4061e0a7-5bcb-4256-96dd-a738e2f54540`，可用 `ocr review --resume 4061e0a7-5bcb-4256-96dd-a738e2f54540` 续跑。
