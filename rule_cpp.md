# C/C++ 编码规范

## 0. 规范等级说明 【补充】

| 等级 | 含义 | 违反后果 |
| --- | --- | --- |
| **〖强制〗** | 必须遵守，CI 或代码评审中拦截 | 不得合入 |
| **〖推荐〗** | 默认遵守，有充分理由可例外，需在评审中说明 | 评审提出意见 |
| **〖参考〗** | 最佳实践，视场景选用 | 无 |

---

# 1. 命名规约

## 1.1 通用命名

- **〖强制〗** 命名必须使用有意义的英文单词，禁止拼音、中文、无意义缩写。
- **〖强制〗** 禁止使用单字符命名，循环变量 `i`、`j`、`k` 除外。
- **〖强制〗** 禁止使用 C/C++ 关键字、标准库常用名作为标识符，如 `std`、`string`、`vector`、`errno`、`assert`、`min`、`max`。
- **〖强制〗** 【补充】禁止使用保留标识符：以下划线开头后跟大写字母（如 `_Value`）、包含双下划线（如 `my__var`）、全局作用域内以下划线开头的名字。这些属于编译器与标准库保留，使用即为未定义行为。
- **〖推荐〗** 布尔变量使用 `is_`、`has_`、`can_`、`should_` 前缀。
- **〖推荐〗** 通用缩写保持词形统一，如 `Http`、`Url`、`Id`，禁止同一项目混用 `HTTP` 与 `Http`。

## 1.2 文件与目录

- **〖强制〗** 文件名、目录名使用小写字母，单词间用下划线分隔，如 `user_service.cpp`、`data_utils/`。
- **〖强制〗** 扩展名统一：C++ 头文件 `.h` 或 `.hpp`（项目二选一）、源文件 `.cpp`；C 头文件 `.h`、源文件 `.c`。
- **〖强制〗** 头文件与源文件成对同名，如 `user_service.h` 与 `user_service.cpp`。
- **〖推荐〗** 目录名使用单数形式，如 `model` 而非 `models`，团队统一后可例外。
- **〖推荐〗** 文件名避免与标准库或系统头文件重名，如 `string.h`、`time.h`、`memory.h`。

## 1.3 命名空间 【补充】

- **〖强制〗** 命名空间使用小写 `snake_case`，顶层命名空间为项目名，如 `myproject::user`。
- **〖强制〗** 所有项目代码必须位于项目命名空间内，禁止向全局命名空间添加符号（`main` 除外）。
- **〖强制〗** 禁止向 `std` 命名空间添加声明（`std::hash` 等标准允许的特化除外）。
- **〖推荐〗** 仅在本文件使用的符号放入匿名命名空间，替代 `static` 全局函数。

## 1.4 类、结构体与异常

- **〖强制〗** 类名、结构体名、类型别名、枚举类型名使用 `UpperCamelCase`，如 `UserService`、`HttpClient`。
- **〖强制〗** 异常类以 `Error` 或 `Exception` 结尾，如 `BusinessError`、`ConfigException`。
- **〖强制〗** 抽象基类以 `Base` 或 `Abstract` 开头，如 `BaseRepository`、`AbstractParser`。
- **〖推荐〗** 测试套件以 `Test` 结尾或开头，项目统一，如 `UserServiceTest`。
- **〖推荐〗** `struct` 仅用于只承载数据、无不变量的类型；有不变量或私有成员时使用 `class`。

## 1.5 函数与变量

- **〖强制〗** 函数名、方法名、局部变量名、参数名使用 `snake_case`，如 `get_user_by_id`、`user_name`。
- **〖强制〗** 【补充】类的非公有成员变量以下划线结尾，如 `user_name_`；`struct` 的公有成员不加下划线。
- **〖推荐〗** 函数名使用动词或动宾结构，如 `fetch_data`、`validate_input`。
- **〖推荐〗** 取值函数可直接用名词，如 `name()`；设值函数使用 `set_name()`。
- **〖推荐〗** 避免使用 `data`、`info`、`temp`、`buf` 等模糊命名。

## 1.6 常量、枚举与宏 【修正】

> 原规范要求常量全大写。在 C/C++ 中全大写约定俗成地属于**宏**，常量也全大写会导致常量被同名宏替换，
> 引发难以排查的编译错误，因此本规范区分常量与宏。

- **〖强制〗** 宏名使用全大写下划线分隔，并带项目前缀，如 `MYPROJECT_ENABLE_TRACE`。
- **〖强制〗** `constexpr` / `const` 常量使用 `k` + `UpperCamelCase`，如 `kMaxRetryCount`、`kDefaultTimeout`。
- **〖强制〗** 枚举成员使用 `k` + `UpperCamelCase`，如 `OrderStatus::kPending`。
- **〖参考〗** 若团队已有存量代码统一使用全大写常量，可保持，但必须保证不与任何宏重名。

## 1.7 模板参数

- **〖强制〗** 模板类型参数使用 `UpperCamelCase`，如 `T`、`ValueType`。
- **〖推荐〗** 模板参数尽量使用有意义的名称，如 `ResponseT`、`Allocator`。
- **〖参考〗** C++20 使用 `concept` 约束模板参数，概念名使用 `UpperCamelCase`，如 `Hashable`。

## 1.8 正例与反例

```cpp
// 正例
namespace myproject::user {

constexpr int kMaxRetryCount = 3;

class UserService {
public:
    std::optional<User> get_user_by_id(std::int64_t user_id) const;

private:
    std::string service_name_;
    bool is_ready_ = false;
};

}  // namespace myproject::user

// 反例
#define maxRetry 3                // 宏名未全大写，且应使用 constexpr
class userService {              // 类名未使用大驼峰
public:
    User* GetUser(int id);       // 函数名未使用 snake_case，返回裸指针所有权不明
    int _Count;                  // 保留标识符
};
```

---

# 2. 代码格式与风格

## 2.1 基础格式

- **〖强制〗** 每行代码不超过 100 个字符，推荐 100 以内、尽量 80~90。
- **〖强制〗** 使用 4 个空格缩进，禁止 Tab。
- **〖强制〗** 文件末尾必须有一个空行。
- **〖强制〗** 禁止行尾多余空格。
- **〖强制〗** 源文件使用 UTF-8 编码（无 BOM），MSVC 需加 `/utf-8` 编译选项。
- **〖强制〗** 使用 `clang-format` 自动格式化，配置文件 `.clang-format` 提交到仓库根目录，禁止手工调整格式（配置样例见附录 A）。

## 2.2 大括号与语句 【补充】

- **〖强制〗** `if`、`else`、`for`、`while`、`do` 的语句体必须使用大括号，即使只有一行。
- **〖强制〗** 每行只写一条语句，每条声明只声明一个变量。
- **〖推荐〗** 左大括号不换行（函数定义可换行，团队统一）。
- **〖推荐〗** 指针与引用符号靠近类型，如 `int* ptr`、`const std::string& name`。

## 2.3 空行

- **〖强制〗** 函数定义之间、类定义之间空一行。
- **〖强制〗** 命名空间结束处加注释，如 `}  // namespace myproject`。
- **〖推荐〗** 函数内逻辑块之间空一行；连续空行不超过 1 行。
- **〖推荐〗** 类内按 `public`、`protected`、`private` 顺序组织，每段内先类型、再构造/析构、再方法、最后数据成员。

## 2.4 运算符与空格

- **〖强制〗** 二元运算符、赋值运算符两侧加空格，如 `a + b`、`x == y`。
- **〖强制〗** 逗号、分号（`for` 内）后加空格，如 `func(a, b, c)`。
- **〖强制〗** 一元运算符与操作数之间不加空格，如 `!is_valid`、`++count`、`*ptr`。
- **〖强制〗** 关键字 `if`、`for`、`while`、`switch` 与左括号之间加一个空格；函数名与左括号之间不加空格。

## 2.5 正例与反例

```cpp
// 正例
double calculate_total(double price, int quantity, double discount = 0.0) {
    return price * quantity * (1.0 - discount);
}

// 反例
double calculate_total( double price,int quantity,double discount=0.0 )
{
	return price*quantity*(1-discount);   // Tab 缩进，空格混乱
}
```

---

# 3. 头文件与包含规约（对应原“导入规约”）

## 3.1 头文件保护与自包含

- **〖强制〗** 每个头文件必须有保护：`#pragma once` 或 `#ifndef` 宏保护（项目统一）。使用宏保护时格式为 `<项目>_<路径>_<文件>_H_`。
- **〖强制〗** 头文件必须自包含：单独 `#include` 该头文件即可编译通过，不依赖包含顺序。
- **〖强制〗** 头文件中禁止 `using namespace xxx;`，禁止定义非 `inline` 的函数或非 `inline` 的全局变量（违反 ODR）。
- **〖强制〗** 禁止 `#include` 源文件（`.cpp`、`.c`）。

## 3.2 包含顺序

- **〖强制〗** `#include` 分为五组，组间空一行，按以下顺序：
  1. 与本源文件对应的头文件（尽早发现头文件不自包含的问题）；
  2. C 系统头文件，如 `<unistd.h>`；
  3. C++ 标准库头文件，如 `<string>`、`<vector>`；
  4. 第三方库头文件，如 `<spdlog/spdlog.h>`；
  5. 本项目头文件，如 `"myproject/core/config.h"`。
- **〖强制〗** 标准库与第三方库使用尖括号 `<>`，本项目头文件使用双引号 `""`，且使用相对于项目 `include/` 根的完整路径，禁止 `../` 相对路径。
- **〖强制〗** C++ 中使用 `<cstdio>`、`<cstring>` 等 C++ 版本头文件，而非 `<stdio.h>`。
- **〖推荐〗** 组内按字母顺序排序，由 `clang-format`（`IncludeBlocks: Regroup`）自动整理。

## 3.3 依赖最小化

- **〖强制〗** 包含所用即所需（Include What You Use）：用到哪个符号就包含其所在头文件，禁止依赖间接包含。
- **〖推荐〗** 头文件中能用前置声明解决的，不包含完整头文件，以减少编译依赖。
- **〖推荐〗** 使用 `include-what-you-use` 或 `clang-tidy misc-include-cleaner` 检查。
- **〖强制〗** 源文件中禁止 `using namespace std;`；可在函数作用域内使用 `using std::string;` 这类具体声明。

```cpp
// 正例：user_service.cpp
#include "myproject/user/user_service.h"

#include <unistd.h>

#include <string>
#include <vector>

#include <fmt/format.h>
#include <spdlog/spdlog.h>

#include "myproject/core/config.h"
#include "myproject/model/user.h"
```

```cpp
// 反例
#include "../model/user.h"     // 相对路径
#include <stdio.h>             // C++ 中应使用 <cstdio>
using namespace std;           // 禁止
#include "helper.cpp"          // 禁止包含源文件
```

---

# 4. 类型与类型安全（对应原“类型注解”）

> 【修正】原规范第 4 章首条“注释必须使用中文”与类型注解无关，已移至第 13 章“注释与文档”。

## 4.1 基本规则

- **〖强制〗** 使用 `nullptr` 表示空指针，禁止 `NULL` 与 `0`。
- **〖强制〗** 禁止 C 风格强制转换 `(int)x`，使用 `static_cast`、`const_cast`、`reinterpret_cast`、`dynamic_cast`；`reinterpret_cast` 与 `const_cast` 必须写明原因注释。
- **〖强制〗** 需要明确位宽时使用 `<cstdint>` 定宽整数，如 `std::int32_t`、`std::uint64_t`；表示大小、下标时使用 `std::size_t`。
- **〖强制〗** 禁止有符号与无符号混合比较和运算（开启 `-Wsign-compare`）。
- **〖强制〗** 禁止隐式窄化转换，使用花括号初始化 `int count{value};` 让编译器检查。
- **〖强制〗** 禁止滥用 `void*` 与类型擦除，使用 `void*` 必须写明原因；C++ 中优先使用模板、`std::variant`、`std::any`。
- **〖强制〗** 可空值使用 `std::optional<T>`；可空的非所有权引用使用 `T*`；不可空的引用使用 `T&`。禁止用魔法值（如 `-1`）表示“无结果”。

## 4.2 const 正确性 【补充】

- **〖强制〗** 不修改对象状态的成员函数必须声明为 `const`。
- **〖强制〗** 不修改的引用、指针参数必须加 `const`，如 `const std::string&`。
- **〖推荐〗** 初始化后不再改变的局部变量声明为 `const` 或 `constexpr`。
- **〖推荐〗** 能在编译期计算的函数声明为 `constexpr`（C++20 可用 `consteval`）。

## 4.3 auto 与类型推导 【补充】

- **〖推荐〗** 类型冗长且显而易见时使用 `auto`，如迭代器、`make_unique` 的结果。
- **〖强制〗** 禁止用 `auto` 隐藏影响语义的类型，如代理类型 `std::vector<bool>::reference`、表达式模板结果。
- **〖强制〗** `auto` 接收引用时必须显式写 `auto&` 或 `const auto&`，避免意外拷贝。

## 4.4 属性标注 【补充】

- **〖推荐〗** 返回值不应被忽略的函数（错误码、新分配资源、纯计算结果）标注 `[[nodiscard]]`。
- **〖推荐〗** 有意未使用的变量标注 `[[maybe_unused]]`，而非 `(void)x`。
- **〖参考〗** 废弃接口使用 `[[deprecated("原因及替代接口")]]`。

```cpp
// 正例
[[nodiscard]] std::optional<User> find_user(std::int64_t user_id);
std::map<std::string, int> process_items(const std::vector<Item>& items);

// 反例
User* find_user(int id);                  // 返回裸指针，不清楚是否可空、谁负责释放
int length = (int)names.size();           // C 风格转换，且可能窄化
if (index < names.size() - 1) { }         // size() 为 0 时下溢为极大值
```

## 4.5 警告抑制（对应原“类型忽略”）

- **〖强制〗** 抑制静态检查必须指定具体规则，如 `// NOLINT(bugprone-narrowing-conversions)`，禁止裸 `// NOLINT`。
- **〖强制〗** 抑制必须写明原因注释。
- **〖强制〗** 使用 `#pragma` 抑制编译器警告时必须成对 `push` / `pop`，范围最小化。
- **〖推荐〗** 优先修复问题，而不是抑制。

---

# 5. 常量与枚举

- **〖强制〗** 禁止魔法值直接出现在代码中，必须定义为常量或枚举（`0`、`1`、`-1`、`nullptr` 在语义明确时除外）。
- **〖强制〗** 常量使用 `constexpr`（或 `const`），禁止使用 `#define` 定义常量。
- **〖强制〗** 枚举使用 `enum class`，禁止无作用域 `enum` 与散落的整数常量。
- **〖强制〗** 【补充】需要固定存储大小或跨模块传输的枚举必须指定底层类型，如 `enum class OrderStatus : std::uint8_t`。
- **〖强制〗** 【补充】头文件中的常量使用 `inline constexpr`（C++17），避免每个翻译单元一份副本。
- **〖推荐〗** 常量按业务模块归类，放在所属模块的命名空间中，不要全部堆放在一个文件。
- **〖推荐〗** 枚举提供 `to_string` 转换函数，便于日志输出。

```cpp
// 正例
enum class OrderStatus : std::uint8_t {
    kPending,
    kPaid,
    kCancelled,
};

inline constexpr int kMaxRetryCount = 3;
inline constexpr std::chrono::seconds kDefaultTimeout{30};

std::string_view to_string(OrderStatus status);
```

```cpp
// 反例
#define MAX_RETRY 3          // 应使用 constexpr
enum { PENDING, PAID };      // 无作用域枚举，污染外层命名空间
if (status == 1) { }         // 魔法值
sleep(30);                   // 魔法值，且单位不明
```

---

# 6. 变量与数据结构

- **〖强制〗** 变量在声明时必须初始化，禁止读取未初始化变量（未定义行为）。
- **〖强制〗** 变量在最小作用域内、首次使用处声明。
- **〖强制〗** 禁止在遍历容器时进行使迭代器失效的修改（如 `vector` 遍历中 `push_back` / `erase`）；需要删除时使用 erase-remove 惯用法或 C++20 `std::erase_if`。
- **〖强制〗** 【补充】禁止返回或保存指向局部变量、临时对象的指针、引用、`std::string_view`、`std::span`。
- **〖推荐〗** 优先使用标准容器：`std::vector`、`std::array`、`std::string`、`std::unordered_map`；禁止使用 C 风格数组与手工管理的动态数组。
- **〖推荐〗** 已知规模的 `vector`、`string` 先 `reserve`。
- **〖推荐〗** 只读字符串参数使用 `std::string_view`，只读连续序列参数使用 `std::span`（C++20）。
- **〖参考〗** 高性能场景可使用 `absl::flat_hash_map`、`boost::container::small_vector` 等。

```cpp
// 正例
std::vector<std::string> add_item(std::string item, std::vector<std::string> items = {}) {
    items.push_back(std::move(item));
    return items;
}

std::erase_if(users, [](const User& user) { return user.is_deleted; });

// 反例
int count;                       // 未初始化
const char* get_name() {
    std::string name = "test";
    return name.c_str();         // 返回悬垂指针
}
for (auto it = users.begin(); it != users.end(); ++it) {
    if (it->is_deleted) {
        users.erase(it);         // 迭代器失效
    }
}
```

> 说明：原规范“禁止可变对象作为默认参数”是 Python 特有问题。C++ 的默认参数每次调用都会重新求值，
> 不存在该问题，但仍需遵守第 7.1 节关于默认参数的规则。

## 6.1 空指针判断

- **〖强制〗** 指针判空使用 `ptr == nullptr` 或 `ptr != nullptr`（或项目统一使用 `if (ptr)`），禁止与 `NULL`、`0` 比较。
- **〖强制〗** 解引用来自外部或可能为空的指针前必须判空。
- **〖强制〗** 访问 `std::optional` 前必须检查 `has_value()`，或使用 `value_or()`。
- **〖推荐〗** 不可能为空的参数使用引用而非指针，从类型上消除判空。
- **〖推荐〗** 使用 `if (count)` 判断时注意整数 `0` 与指针语义的区别，非布尔类型建议显式比较。

## 6.2 拷贝与移动

- **〖强制〗** 类持有资源时必须明确拷贝语义：深拷贝、禁止拷贝（`= delete`）或共享（`shared_ptr`），禁止依赖编译器生成的浅拷贝。
- **〖强制〗** 被 `std::move` 后的对象只允许销毁或重新赋值，禁止继续读取其值。
- **〖推荐〗** 大对象按值传入后需要保存时，使用 `std::move` 转移，避免多余拷贝。
- **〖推荐〗** 优先使用不可变对象（`const` 成员、只读接口），减少拷贝与同步。

---

# 7. 函数与方法

- **〖强制〗** 函数职责单一，禁止一个函数做多件不相关的事。
- **〖强制〗** 函数参数不超过 5 个，超过时使用结构体参数对象。
- **〖强制〗** 禁止使用可修改的全局变量与非 `const` 静态变量传递状态；确需全局状态时封装在类中并通过依赖注入传递。
- **〖强制〗** 【补充】禁止返回局部对象的引用或指针。
- **〖推荐〗** 函数总行数不超过 50 行，圈复杂度不超过 10。
- **〖推荐〗** 优先使用无副作用的纯函数。
- **〖推荐〗** 小而频繁调用的函数可定义在头文件中并 `inline`，但不依赖 `inline` 做性能优化，由编译器决定。
- **〖参考〗** 包装函数（如重试、计时）使用模板与完美转发，保留被包装函数的参数与返回类型。

```cpp
// 正例：保留原函数签名的重试包装
template <typename Func, typename... Args>
auto retry(int times, Func&& func, Args&&... args) {
    for (int attempt = 1; attempt < times; ++attempt) {
        try {
            return std::invoke(func, args...);
        } catch (const TransientError& error) {
            spdlog::warn("第 {} 次尝试失败: {}", attempt, error.what());
        }
    }
    // 最后一次不再捕获，异常直接向上传递
    return std::invoke(std::forward<Func>(func), std::forward<Args>(args)...);
}
```

## 7.1 参数 【补充】

- **〖强制〗** 参数传递规则：
  - 廉价拷贝的类型（内置类型、`string_view`、`span`、小于等于 16 字节的平凡类型）按值传递；
  - 只读的其他类型按 `const T&` 传递；
  - 需要保存一份副本的参数按值传递并 `std::move`；
  - 需要修改的参数按 `T&` 传递；
  - 转移所有权使用 `std::unique_ptr<T>` 按值传递。
- **〖强制〗** 禁止使用输出参数返回结果，优先使用返回值（多个值见 7.2）。
- **〖强制〗** 虚函数禁止使用默认参数（默认参数静态绑定，与虚函数动态绑定冲突）。
- **〖推荐〗** 参数命名清晰，避免 `a`、`b`、`c`；多个同类型参数易混淆时使用强类型或参数结构体。
- **〖参考〗** C++20 可使用指定初始化器模拟关键字参数。

```cpp
struct CreateUserParams {
    std::string name;
    int age = 0;
};

User create_user(const CreateUserParams& params);

auto user = create_user({.name = "alice", .age = 18});   // C++20 指定初始化器
```

## 7.2 返回值

- **〖强制〗** 函数返回值类型必须明确；公有接口禁止使用 `auto` 推导返回类型（模板除外）。
- **〖推荐〗** 可能失败的函数使用 `std::optional<T>`（只关心有无）或 `std::expected<T, E>`（C++23，低版本使用 `tl::expected`）返回，而非混合返回魔法值。
- **〖推荐〗** 返回多个值时使用具名结构体，调用方可用结构化绑定；避免使用 `std::pair` / `std::tuple`（成员无意义名称）。
- **〖推荐〗** 依赖返回值优化（RVO），禁止对返回的局部变量写 `return std::move(local);`。

---

# 8. 面向对象与数据类

- **〖强制〗** 优先使用组合，避免过深的继承层次，继承不超过 3 层。
- **〖强制〗** 构造函数中禁止做耗时操作或 I/O；可能失败的初始化使用工厂函数返回 `std::optional` / `std::expected` / 智能指针。
- **〖强制〗** 【补充】构造函数和析构函数中禁止调用虚函数（此时不会动态分派）。
- **〖强制〗** 【补充】作为多态基类的类必须声明 `public virtual` 析构函数，或 `protected` 非虚析构函数。
- **〖强制〗** 【补充】重写虚函数必须标注 `override`（或 `final`），禁止同时写 `virtual` 与 `override`。
- **〖强制〗** 【补充】单参数构造函数和转换运算符必须声明为 `explicit`（有意的隐式转换需注释说明）。
- **〖强制〗** 【补充】禁止按值传递或保存多态对象（对象切片），使用引用或智能指针。
- **〖强制〗** 重载 `operator==` 时，若该类型用作哈希容器的键，必须同时特化 `std::hash`，并保证相等的对象哈希值相等。
- **〖推荐〗** 数据载体使用 `struct` + 聚合初始化，C++20 可使用 `= default` 生成比较运算符。
- **〖推荐〗** 成员变量使用默认成员初始化器 `int count_ = 0;`，构造函数初始化列表顺序与声明顺序一致。
- **〖推荐〗** 不暴露可变内部状态：返回 `const T&` 或拷贝，而非非常量引用或指针。
- **〖参考〗** 使用纯虚函数定义接口类，接口类不含数据成员。

## 8.1 特殊成员函数（Rule of 0 / 3 / 5）【补充】

- **〖强制〗** 遵循 Rule of 0：优先用 RAII 成员（智能指针、容器）管理资源，使类无需自定义任何特殊成员函数。
- **〖强制〗** 遵循 Rule of 5：一旦自定义了析构函数、拷贝构造、拷贝赋值、移动构造、移动赋值中的任意一个，必须显式声明全部五个（可 `= default` 或 `= delete`）。
- **〖强制〗** 移动构造与移动赋值必须声明 `noexcept`，否则标准容器扩容时会退化为拷贝。
- **〖强制〗** 拷贝赋值必须正确处理自赋值。

```cpp
// 正例
struct User {
    std::int64_t id = 0;
    std::string name;
    std::string email;

    bool operator==(const User&) const = default;   // C++20
};

class FileHandle {
public:
    explicit FileHandle(const std::filesystem::path& path);
    ~FileHandle();

    FileHandle(const FileHandle&) = delete;
    FileHandle& operator=(const FileHandle&) = delete;
    FileHandle(FileHandle&& other) noexcept;
    FileHandle& operator=(FileHandle&& other) noexcept;

private:
    int file_descriptor_ = -1;
};
```

## 8.2 运算符重载（对应原“魔术方法”）

- **〖强制〗** 重载运算符必须符合直觉语义，如 `+` 不得修改操作数，`==` 必须满足自反、对称、传递。
- **〖强制〗** 禁止重载 `&&`、`||`、`,`、一元 `&`（会破坏短路求值或取地址语义）。
- **〖推荐〗** 为调试与日志提供 `to_string()` 或 `operator<<`，C++20 起可特化 `std::formatter`。
- **〖推荐〗** 对称的二元运算符定义为非成员函数（可为友元），以支持左操作数的隐式转换。

---

# 9. 内存与资源管理 【补充，全章新增】

> Python 由垃圾回收管理内存，C/C++ 需要开发者负责，这是 C/C++ 缺陷与安全漏洞的首要来源。

- **〖强制〗** 所有资源（内存、文件、锁、套接字、句柄）必须由 RAII 对象管理，在析构函数中释放。
- **〖强制〗** 禁止裸 `new` / `delete`；使用 `std::make_unique`、`std::make_shared` 和标准容器。
- **〖强制〗** 所有权语义通过类型表达：
  - 独占所有权：`std::unique_ptr<T>`（默认选择）；
  - 共享所有权：`std::shared_ptr<T>`（确有必要时）；
  - 非所有权观察：`T*`、`T&`、`std::weak_ptr<T>`。
- **〖强制〗** 裸指针一律视为“不拥有”，禁止通过裸指针 `delete` 对象。
- **〖强制〗** `shared_ptr` 可能形成循环引用时，必须用 `weak_ptr` 打破环。
- **〖强制〗** `new[]` 必须与 `delete[]` 配对，`malloc` 必须与 `free` 配对，禁止混用（C++ 中两者均应避免直接使用）。
- **〖强制〗** 与 C 接口交互时，使用带自定义删除器的 `unique_ptr` 托管 C 资源。
- **〖推荐〗** 函数参数不需要所有权时传 `T&` / `T*`，而非智能指针。
- **〖推荐〗** 禁止 `std::shared_ptr<T>(new T)`，避免两次分配及异常安全问题。

```cpp
// 正例
auto user = std::make_unique<User>();

struct FileCloser {
    void operator()(std::FILE* file) const noexcept { std::fclose(file); }
};
using FilePtr = std::unique_ptr<std::FILE, FileCloser>;

FilePtr open_file(const char* path) {
    return FilePtr{std::fopen(path, "rb")};
}

// 反例
User* user = new User();
process(user);          // 若抛出异常则内存泄漏
delete user;
```

---

# 10. 控制语句

- **〖强制〗** 禁止在 `if`、`while` 条件中赋值；需要时使用 C++17 带初始化的 `if (auto it = map.find(key); it != map.end())`。
- **〖强制〗** `switch` 必须有 `default` 分支（对 `enum class` 全覆盖时可省略，但须开启 `-Wswitch-enum`）；有意贯穿的 `case` 必须标注 `[[fallthrough]]`。
- **〖强制〗** 禁止使用 `goto`（C 语言资源清理场景除外，见第 23 章）。
- **〖强制〗** 禁止与 `true`、`false` 显式比较，如 `if (is_active == true)`。
- **〖强制〗** 【补充】浮点数禁止直接用 `==` 比较，使用误差范围判断。
- **〖推荐〗** 使用卫语句减少嵌套，嵌套不超过 4 层。
- **〖推荐〗** 多分支使用 `switch`、查找表或多态，避免长 `if-else if` 链。
- **〖推荐〗** 遍历容器优先使用范围 `for` 或标准算法（`std::ranges`），避免手写下标循环。
- **〖推荐〗** 循环内避免重复计算不变表达式。

```cpp
// 正例
double get_discount(const User& user) {
    if (!user.is_active) {
        return 0.0;
    }
    if (user.is_vip) {
        return kVipDiscount;
    }
    return kDefaultDiscount;
}

// 反例
if (user.is_active == true) { }      // 冗余比较
if (ratio == 0.3) { }                 // 浮点数直接比较
if (count = 0) { }                    // 条件中误赋值
```

---

# 11. 错误处理与异常（对应原“异常处理”）

## 11.1 错误处理策略 【补充】

- **〖强制〗** 项目必须明确统一的错误处理策略并写入 README：
  - 使用异常（默认）：适用于一般业务代码；
  - 禁用异常（`-fno-exceptions`）：适用于嵌入式、实时系统、游戏引擎等，统一使用 `std::expected` / 错误码。
- **〖强制〗** 同一模块内禁止混用多种错误表示方式；跨策略边界（如 C 接口）必须进行转换。
- **〖推荐〗** 可预期的失败（查不到、输入格式错误）使用返回值；不可预期或无法在本地处理的失败使用异常。

## 11.2 异常使用规则

- **〖强制〗** 按值抛出、按 `const` 引用捕获：`throw BusinessError{...};`、`catch (const BusinessError& error)`。
- **〖强制〗** 禁止抛出内置类型或指针，如 `throw -1;`、`throw "error";`、`throw new Error();`。
- **〖强制〗** 禁止空的 `catch (...) {}`；`catch (...)` 只允许在线程入口、`main`、C 接口边界使用，且必须记录日志或转换。
- **〖强制〗** 捕获后必须处理、记录或重新抛出，禁止吞掉异常。
- **〖强制〗** 原样重新抛出使用 `throw;`，禁止 `throw error;`（会切片并丢失原类型）；包装后抛出需保留原因时使用 `std::throw_with_nested`。
- **〖强制〗** 禁止用异常做正常流程控制。
- **〖强制〗** 【补充】析构函数、移动操作、`swap` 必须不抛异常（标注 `noexcept`）。
- **〖强制〗** 【补充】异常禁止跨越 C 接口、回调到 C 库、线程边界传播；线程间传递使用 `std::exception_ptr`。
- **〖推荐〗** 函数提供明确的异常安全保证（基本保证 / 强保证 / 不抛保证），并在文档中注明。
- **〖推荐〗** 对外接口统一异常转换，避免泄露内部实现细节。

```cpp
// 正例
try {
    auto response = http_client.fetch(url);
} catch (const HttpError& error) {
    spdlog::error("获取数据失败: url={}, reason={}", url, error.what());
    std::throw_with_nested(ServiceError{"fetch data failed"});
}
```

```cpp
// 反例
try {
    auto response = http_client.fetch(url);
} catch (...) {      // 捕获所有异常
}                    // 吞异常
```

## 11.3 自定义异常

- **〖强制〗** 项目必须定义基础异常类 `AppError`，继承自 `std::runtime_error`（或 `std::exception`）。
- **〖推荐〗** 业务异常携带错误码与上下文。
- **〖推荐〗** 异常信息避免包含敏感数据。

```cpp
class AppError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class BusinessError : public AppError {
public:
    BusinessError(std::string code, const std::string& message)
        : AppError(fmt::format("[{}] {}", code, message)), code_(std::move(code)) {}

    [[nodiscard]] const std::string& code() const noexcept { return code_; }

private:
    std::string code_;
};
```

## 11.4 断言 【补充】

- **〖强制〗** `assert` 只用于检查程序内部不变量（“不可能发生”的情况），禁止用于校验外部输入。
- **〖强制〗** `assert` 中禁止包含有副作用的表达式（Release 构建中会被移除）。
- **〖推荐〗** 编译期可确定的条件使用 `static_assert`。

---

# 12. 日志规约

- **〖强制〗** 使用日志库（推荐 `spdlog`，或 `glog`），禁止使用 `printf`、`std::cout`、`std::cerr` 输出业务日志。
- **〖强制〗** 日志使用占位符格式化，如 `spdlog::info("user_id={}", user_id)`；禁止先拼接字符串再传入，禁止把外部输入直接作为格式串。
- **〖强制〗** 禁止记录敏感信息，如密码、密钥、Token、身份证号、银行卡号。
- **〖强制〗** 记录异常日志时必须包含异常类型或 `what()` 信息及业务上下文。
- **〖推荐〗** 高频路径的 DEBUG/TRACE 日志使用宏（如 `SPDLOG_DEBUG`），可在编译期剔除。
- **〖推荐〗** 使用结构化日志（JSON 格式）。
- **〖推荐〗** 日志级别使用规范：TRACE、DEBUG、INFO、WARN、ERROR、CRITICAL。
- **〖推荐〗** 生产环境禁止输出 DEBUG 日志。

```cpp
// 正例
spdlog::info("用户登录成功: user_id={}", user_id);
spdlog::error("处理订单失败: order_id={}, reason={}", order_id, error.what());

// 反例
std::cout << "user login success: " << user_id << std::endl;   // 禁止 cout
spdlog::info("user login: " + user_name);                         // 拼接字符串
spdlog::info(user_input);                                         // 外部输入作格式串
```

## 12.1 日志配置

- **〖强制〗** 日志初始化与配置集中在程序入口统一完成，禁止散落在业务代码中。
- **〖推荐〗** 日志级别、输出目标通过配置文件或环境变量控制。
- **〖推荐〗** 容器化部署时日志输出到 stdout/stderr，由平台收集；否则按大小或时间滚动。
- **〖推荐〗** 高吞吐场景使用异步日志，并保证程序退出前刷新（`spdlog::shutdown()`）。

---

# 13. 注释与文档

- **〖强制〗** 注释必须使用中文。（【修正】原规范第 4 章与第 12 章重复出现此条，统一在此）
- **〖强制〗** 专有名词、标识符、错误码在注释中保留原文，如“调用 `fetch_data` 失败时返回 `kTimeout`”。
- **〖强制〗** 每个源文件、头文件开头必须添加文件头注释：

```cpp
/**
 * @file        user_service.cpp
 * @author      Cetrp
 * @date        2026-09-01 10:00
 * @brief       用户服务实现，提供用户查询与注册功能
 * @copyright   Copyright (c) 2026 Cetrp. All rights reserved.
 */
```

- **〖强制〗** 公共头文件中的类、函数、枚举必须写文档注释。
- **〖强制〗** 文档注释统一使用 Doxygen 风格（`/** ... */` 与 `@param`、`@return`、`@throws` 等标签）。
- **〖强制〗** 注释必须与代码同步更新，禁止过期注释；禁止提交被注释掉的代码。
- **〖强制〗** 【补充】文档注释必须说明：参数取值范围与所有权、返回值含义、可能抛出的异常、是否线程安全。
- **〖推荐〗** 文档注释写在头文件声明处，实现文件中只写实现细节注释。
- **〖推荐〗** 复杂逻辑、边界条件、算法来源必须注释说明。
- **〖推荐〗** 使用 `// TODO(负责人): 说明`、`// FIXME(#issue编号): 说明` 标注待办。
- **〖参考〗** 使用 Doxygen 自动生成 API 文档。

```cpp
/**
 * @brief 计算两个数的商。
 *
 * @param dividend 被除数。
 * @param divisor  除数，不能为 0。
 * @return 两数相除的结果。
 * @throws std::invalid_argument 当 divisor 为 0 时抛出。
 * @note 线程安全。
 */
double divide(double dividend, double divisor) {
    if (divisor == 0.0) {
        throw std::invalid_argument("divisor must not be zero");
    }
    return dividend / divisor;
}
```

## 13.1 README 与 CHANGELOG

- **〖强制〗** 项目根目录必须有 `README.md`。
- **〖推荐〗** README 包含：项目简介、依赖与编译器版本要求、构建、使用、配置、开发、测试、错误处理策略、许可证。
- **〖推荐〗** 使用 `CHANGELOG.md` 记录版本变更；库项目需注明 ABI 是否兼容。
- **〖参考〗** 使用 `git-cliff` 或 `commitizen` 自动生成 CHANGELOG。

---

# 14. 单元测试

- **〖强制〗** 新代码必须包含单元测试，核心逻辑行覆盖率不低于 80%。
- **〖强制〗** 测试必须独立、可重复、无外部依赖，遵循 AIR 原则（Automatic、Independent、Repeatable）。
- **〖强制〗** 禁止测试之间相互依赖执行顺序（可用 `--gtest_shuffle` 验证）。
- **〖强制〗** 禁止在测试中使用固定 `sleep`，使用条件变量、`std::future::wait_for` 或可注入的时钟。
- **〖强制〗** 【补充】CI 中测试必须在 AddressSanitizer + UndefinedBehaviorSanitizer 下运行一遍；含并发的模块还需在 ThreadSanitizer 下运行。
- **〖推荐〗** 使用 GoogleTest（或 Catch2），遵循 AAA 模式：Arrange、Act、Assert。
- **〖推荐〗** 使用参数化测试（`TEST_P` / `INSTANTIATE_TEST_SUITE_P`）。
- **〖推荐〗** 使用 Test Fixture 管理测试资源，使用 GoogleMock 隔离外部依赖；为此业务代码应依赖接口而非具体类。
- **〖推荐〗** 测试文件放在 `tests/`，目录结构与 `src/` 对应。
- **〖参考〗** 使用 `gcov` / `llvm-cov` + `lcov` 统计覆盖率；使用 libFuzzer 对解析类代码做模糊测试。

```cpp
// 正例
struct AddCase {
    int lhs;
    int rhs;
    int expected;
};

class AddTest : public ::testing::TestWithParam<AddCase> {};

TEST_P(AddTest, ReturnsSumOfTwoNumbers) {
    const auto& [lhs, rhs, expected] = GetParam();
    EXPECT_EQ(add(lhs, rhs), expected);
}

INSTANTIATE_TEST_SUITE_P(Basic, AddTest,
                         ::testing::Values(AddCase{1, 2, 3}, AddCase{0, 0, 0},
                                           AddCase{-1, 1, 0}));
```

## 14.1 测试命名

- **〖强制〗** 测试文件命名 `<被测文件>_test.cpp`，如 `user_service_test.cpp`。
- **〖强制〗** 测试用例命名使用 `UpperCamelCase` 描述行为，如 `TEST(UserServiceTest, LoginWithInvalidPasswordThrowsError)`。
- **〖强制〗** GoogleTest 用例名中禁止包含下划线（GoogleTest 官方限制）。

## 14.2 测试隔离

- **〖强制〗** 测试不得依赖真实数据库、网络、文件系统，必要时使用 SQLite 内存库。
- **〖推荐〗** 必须使用文件时，在 `std::filesystem::temp_directory_path()` 下创建唯一临时目录，并在 TearDown 中清理。
- **〖推荐〗** 网络依赖通过接口抽象后用 Mock 替换，或使用本地桩服务。

---

# 15. 安全规约

- **〖强制〗** 禁止硬编码密码、密钥、Token，使用环境变量或密钥管理服务。
- **〖强制〗** 禁止使用 `system()`、`popen()` 执行拼接了外部输入的命令；必须执行外部程序时使用 `execve` 系列并传参数数组。
- **〖强制〗** 禁止对不可信数据使用无校验的二进制反序列化（如直接 `memcpy` 到结构体、Boost.Serialization）；使用带校验的格式（Protobuf、FlatBuffers Verifier 等）。
- **〖强制〗** SQL 必须使用预编译语句与参数绑定，禁止字符串拼接。
- **〖强制〗** 用户输入必须校验长度、范围、格式后再使用。
- **〖强制〗** 文件路径必须规范化（`std::filesystem::weakly_canonical`）并校验位于允许的根目录内，防止路径穿越；上传文件必须校验类型与大小。
- **〖强制〗** 对外接口必须做权限校验、频率限制、防重放。
- **〖推荐〗** 密码使用 `argon2`、`bcrypt` 哈希，禁止明文或 MD5、SHA1。
- **〖推荐〗** 加密使用成熟库（OpenSSL、libsodium），禁止自行实现加密算法。

## 15.1 内存安全 【补充】

- **〖强制〗** 禁止使用不安全的 C 函数：`gets`、`strcpy`、`strcat`、`sprintf`、`vsprintf`、`scanf("%s")`、`strtok`（非线程安全）、`atoi`（无错误检测）。替代方案：`std::string`、`snprintf`、`std::from_chars`、`strtol`。
- **〖强制〗** 所有数组、缓冲区访问必须保证不越界；外部传入的长度、下标必须先校验。
- **〖强制〗** 涉及外部输入的整数运算（尤其是计算分配大小）必须检查溢出，如使用 `__builtin_mul_overflow`。
- **〖强制〗** `printf` 系列与日志的格式串必须是字面量，禁止使用外部输入作为格式串。
- **〖强制〗** 释放后禁止再次使用（Use-After-Free）、禁止重复释放（Double Free）。
- **〖推荐〗** 存放密钥、密码的内存使用后用 `explicit_bzero` / `OPENSSL_cleanse` 清零（普通 `memset` 可能被优化掉）。

## 15.2 编译加固 【补充】

- **〖强制〗** Release 构建开启以下加固选项（GCC/Clang）：
  - `-fstack-protector-strong`
  - `-D_FORTIFY_SOURCE=2`（需开启优化）
  - `-fPIE -pie`
  - `-Wl,-z,relro,-z,now`
  - `-Wl,-z,noexecstack`
- **〖推荐〗** 使用 `clang-tidy`、`cppcheck`、`CodeQL` 或 `Coverity` 做静态分析，CI 中阻断新增高危问题。
- **〖推荐〗** 使用 `gitleaks` 扫描密钥泄露。

## 15.3 密钥管理

- **〖强制〗** 密钥不得出现在代码、配置、日志、Git 历史、可执行文件中。
- **〖推荐〗** 使用 Vault、云厂商 KMS / Secrets Manager 管理密钥。
- **〖推荐〗** 提供配置模板文件（如 `config.example.yaml`、`.env.example`），不提交真实配置。

## 15.4 依赖安全

- **〖强制〗** CI 必须执行依赖漏洞扫描（如 OSV-Scanner、`conan audit`、GitHub Dependabot）。
- **〖强制〗** 第三方库通过包管理器（vcpkg、Conan）引入并锁定版本，禁止从网络随意复制源码进仓库；必须内置的源码放在 `third_party/` 并注明来源与版本。
- **〖推荐〗** 定期升级依赖，修复高危漏洞。

---

# 16. 并发

- **〖强制〗** 禁止为每个任务手动创建线程，必须使用线程池（如 `boost::asio::thread_pool`、`BS::thread_pool` 或项目统一实现）。
- **〖强制〗** 线程必须设置有意义的名称，便于调试与性能分析（Linux 下 `pthread_setname_np`，名称不超过 15 字符）。
- **〖强制〗** 多线程共享的可变数据必须加锁或使用 `std::atomic`；数据竞争是未定义行为。
- **〖强制〗** 加锁必须使用 RAII：`std::lock_guard`、`std::unique_lock`、`std::scoped_lock`，禁止手动 `lock()` / `unlock()`。
- **〖强制〗** 同时获取多把锁时使用 `std::scoped_lock` 或保证全局一致的加锁顺序，避免死锁。
- **〖强制〗** 【补充】禁止 `std::thread::detach()`；线程必须被 `join`，优先使用 C++20 `std::jthread`。
- **〖强制〗** 【补充】`std::condition_variable::wait` 必须带谓词，防止虚假唤醒与丢失通知。
- **〖强制〗** 【补充】持有锁期间禁止调用外部回调、执行 I/O 或其他耗时操作。
- **〖推荐〗** I/O 密集型使用异步 I/O（Boost.Asio、libuv）或线程池；CPU 密集型线程数取 `std::thread::hardware_concurrency()`。
- **〖推荐〗** 读多写少场景使用 `std::shared_mutex`。
- **〖推荐〗** 非专家禁止使用 `memory_order_relaxed` 等弱内存序，默认使用 `seq_cst`。
- **〖参考〗** 优先通过消息传递（队列）而非共享内存进行线程通信。

```cpp
// 正例
class Counter {
public:
    void increment() {
        std::lock_guard<std::mutex> lock(mutex_);
        ++count_;
    }

    [[nodiscard]] int value() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return count_;
    }

private:
    mutable std::mutex mutex_;
    int count_ = 0;
};
```

## 16.1 异步规范

- **〖强制〗** 事件循环线程（如 Asio 的 `io_context`）中禁止调用阻塞 I/O 与阻塞等待，阻塞操作投递到工作线程池。
- **〖强制〗** 异步回调或协程中禁止使用 `std::this_thread::sleep_for`，应使用定时器（如 `asio::steady_timer`）。
- **〖强制〗** 异步回调捕获对象时必须保证生命周期，使用 `shared_from_this()` 或 `weak_ptr`，禁止捕获可能失效的 `this` 或局部变量引用。
- **〖推荐〗** 所有异步操作设置超时。
- **〖参考〗** C++20 协程配合 Asio `co_await` 编写异步代码，减少回调嵌套。

---

# 17. 数据库访问

- **〖强制〗** 禁止在循环中逐条查询，避免 N+1，使用批量查询或 `IN` / `JOIN`。
- **〖强制〗** 事务必须明确边界，使用 RAII 事务对象：析构时未提交则自动回滚。
- **〖强制〗** 禁止使用 `SELECT *`，必须明确字段。
- **〖强制〗** 分页查询必须使用 `LIMIT` / `OFFSET` 或游标，避免全表扫描。
- **〖强制〗** 所有 SQL 使用预编译语句与参数绑定。
- **〖推荐〗** 使用成熟的客户端库或 ORM（如 `libpqxx`、`SOCI`、`sqlpp11`、`ODB`）。
- **〖推荐〗** 高频查询字段建立索引，联合索引遵循最左前缀。
- **〖推荐〗** 软删除字段使用 `is_deleted`，并建立索引。
- **〖参考〗** 复杂查询使用 CTE、窗口函数，避免多层嵌套子查询。

```cpp
// 正例（libpqxx）
pqxx::work transaction(connection);
auto row = transaction.exec_params1(
    "SELECT id, name, email FROM users WHERE id = $1", user_id);
transaction.commit();

// 反例
auto sql = "SELECT * FROM users WHERE id = " + std::to_string(user_id);   // 拼接 SQL
```

## 17.1 连接池

- **〖强制〗** 必须使用连接池，禁止每次请求新建连接。
- **〖强制〗** 连接借出后必须由 RAII 对象归还，禁止手动归还。
- **〖推荐〗** 配置合理的连接池大小、获取超时、空闲回收策略与健康检查。
- **〖推荐〗** 监控连接池使用率与慢查询。

---

# 18. 配置管理

- **〖强制〗** 配置与代码分离，禁止硬编码地址、端口、路径、超时等配置。
- **〖强制〗** 敏感配置使用环境变量或密钥管理服务。
- **〖强制〗** 【补充】配置必须在程序启动时一次性加载并校验（类型、范围、必填项），校验失败立即退出并输出明确错误，禁止运行中途才发现配置错误。
- **〖推荐〗** 配置文件使用 YAML / TOML / JSON（如 `yaml-cpp`、`toml++`、`nlohmann/json`），加载为强类型的配置结构体。
- **〖推荐〗** 配置对象加载后只读，以 `const` 引用传递给各模块，禁止做成可修改的全局单例。
- **〖推荐〗** 配置分层：默认配置、环境配置、本地覆盖、命令行参数（优先级递增）。

```cpp
struct Settings {
    std::string database_url;
    bool is_debug = false;
    std::chrono::seconds request_timeout{30};
};

// 启动时加载并校验，失败抛出 ConfigException
[[nodiscard]] Settings load_settings(const std::filesystem::path& config_path);
```

---

# 19. 性能与优化

- **〖强制〗** 禁止过早优化，必须先测量再优化，并保留优化前后的基准数据。
- **〖强制〗** 禁止在循环内做重复计算、重复 I/O、重复查询、重复内存分配。
- **〖强制〗** 【补充】禁止为了性能依赖未定义行为或编译器特定行为。
- **〖推荐〗** 使用 `perf`、`Valgrind/Callgrind`、`VTune`、`Tracy` 定位瓶颈；使用 Google Benchmark 编写微基准测试。
- **〖推荐〗** 避免不必要的拷贝：按 `const&` 传参、使用移动语义、`emplace_back`。
- **〖推荐〗** 容器预先 `reserve`；字符串拼接使用 `reserve` + `append` 或 `fmt::format`，避免循环中反复 `+` 产生临时对象。
- **〖推荐〗** 注意数据局部性，热点数据优先使用连续存储（`vector` 优于 `list`）。
- **〖推荐〗** 使用缓存：本地缓存（LRU）、Redis。
- **〖参考〗** 性能关键路径可使用 SIMD、无锁数据结构、内存池，但必须有基准数据证明收益并充分测试。

```cpp
// 正例
std::string result;
result.reserve(kExpectedLength);
for (int i = 0; i < kCount; ++i) {
    result.append(std::to_string(i));
}

// 反例
std::string result;
for (int i = 0; i < kCount; ++i) {
    result = result + std::to_string(i);    // 每次产生临时对象，O(n²)
}
```

---

# 20. 未定义行为与可移植性 【补充，全章新增】

- **〖强制〗** 禁止编写任何依赖未定义行为（UB）的代码。常见 UB 包括：
  - 有符号整数溢出；
  - 数组越界、解引用空指针或悬垂指针；
  - 读取未初始化变量；
  - 数据竞争；
  - 违反严格别名规则（用不相关类型的指针访问同一内存，应改用 `std::memcpy` 或 C++20 `std::bit_cast`）；
  - 移位位数大于等于类型位宽或为负数；
  - 同一表达式中对同一变量无序地多次修改，如 `i = i++ + 1`。
- **〖强制〗** 编译必须开启警告并视为错误（GCC/Clang）：`-Wall -Wextra -Wpedantic -Werror`，以及 `-Wshadow -Wconversion -Wsign-conversion -Wnon-virtual-dtor -Wold-style-cast -Woverloaded-virtual -Wnull-dereference -Wformat=2`；MSVC 使用 `/W4 /WX /permissive-`。
- **〖强制〗** CI 必须包含 Sanitizer 构建：`-fsanitize=address,undefined`；并发代码另加 `-fsanitize=thread`（不能与 address 同时使用）。
- **〖强制〗** 禁止使用编译器扩展语法（如 GCC 变长数组、语句表达式），确需使用时封装并加注释。
- **〖推荐〗** 网络、文件中的二进制数据必须显式处理字节序（C++20 `std::endian`）与对齐，禁止直接把结构体按内存布局读写。
- **〖推荐〗** 至少在两种编译器（GCC 与 Clang，或加 MSVC）上编译通过。

---

# 21. 构建与工程结构 【补充，全章新增】

- **〖强制〗** 使用 CMake（3.20+）作为构建系统，采用基于 target 的现代写法：`target_include_directories`、`target_link_libraries`、`target_compile_options`；禁止使用全局的 `include_directories`、`add_definitions`、`link_libraries`。
- **〖强制〗** 在 CMake 中固定语言标准且禁止编译器扩展：`CMAKE_CXX_STANDARD 20`、`CMAKE_CXX_STANDARD_REQUIRED ON`、`CMAKE_CXX_EXTENSIONS OFF`。
- **〖强制〗** 必须使用源外构建（`cmake -B build`），构建目录加入 `.gitignore`。
- **〖强制〗** 第三方依赖通过 vcpkg（manifest 模式 `vcpkg.json`）或 Conan 管理，并锁定版本。
- **〖推荐〗** 导出 `compile_commands.json`（`CMAKE_EXPORT_COMPILE_COMMANDS ON`）供 clang-tidy、IDE 使用。
- **〖推荐〗** 使用 `CMakePresets.json` 统一 Debug、Release、Sanitizer 等构建配置。
- **〖推荐〗** 目录结构：

```text
myproject/
├── CMakeLists.txt
├── CMakePresets.json
├── vcpkg.json
├── .clang-format
├── .clang-tidy
├── README.md
├── CHANGELOG.md
├── include/myproject/      # 公共头文件
├── src/                    # 源文件与私有头文件
├── tests/                  # 单元测试，结构与 src/ 对应
├── benchmarks/             # 性能基准测试
├── third_party/            # 必须内置的第三方源码（注明来源与版本）
└── docs/
```

---

# 22. Git 与提交规约

- **〖强制〗** 提交信息使用 Conventional Commits：`feat:`、`fix:`、`docs:`、`refactor:`、`test:`、`perf:`、`build:`、`ci:`、`chore:`。
- **〖强制〗** 禁止提交密钥、密码、Token、大文件，以及构建产物（`build/`、`*.o`、`*.a`、`*.so`、`*.exe`）。
- **〖强制〗** 提交前必须通过 pre-commit 检查，至少包含：`clang-format` 格式检查、`clang-tidy` 静态检查、密钥扫描。
- **〖推荐〗** 一个提交只做一件事，提交信息清晰描述变更。
- **〖推荐〗** 分支命名：`feature/xxx`、`bugfix/xxx`、`hotfix/xxx`。
- **〖推荐〗** 大型二进制资源使用 Git LFS 管理。
- **〖参考〗** 使用 `git-cliff` 或 `commitizen` 自动生成 CHANGELOG。

```text
feat(user): add user login API
fix(order): correct total price calculation
build(cmake): enable sanitizer preset
docs(readme): update build guide
```

## 22.1 分支策略

> 【修正】原规范此处编号误写为“192.1”。

- **〖推荐〗** 主分支保护，禁止直接 push，合并必须经过代码评审与 CI。
- **〖推荐〗** 功能分支从主分支切出，合并前 rebase。
- **〖推荐〗** 发布使用 tag，如 `v1.0.0`，遵循语义化版本；库项目破坏 ABI 时必须升级主版本号。

---

# 23. C 语言专项 【补充，全章新增】

> 以下条目适用于纯 C 项目，与前文冲突时以本章为准；未提及的规则沿用前文。

## 23.1 命名

- **〖强制〗** C 没有命名空间，所有对外函数、类型、宏必须带模块前缀，如 `user_service_get_by_id()`、`user_service_t`、`USER_SERVICE_MAX_COUNT`。
- **〖强制〗** 仅在本文件使用的函数与全局变量必须声明为 `static`。
- **〖推荐〗** 结构体类型使用 `typedef`，以 `_t` 结尾（注意 POSIX 保留 `_t` 后缀，与系统冲突时改用 `UpperCamelCase`，项目统一）。
- **〖推荐〗** 使用不透明指针（opaque pointer）隐藏结构体实现，头文件中只声明 `typedef struct user_service user_service_t;`。

## 23.2 宏

- **〖强制〗** 能用 `static inline` 函数、`enum`、`const` 实现的，禁止使用宏。
- **〖强制〗** 函数式宏的每个参数及整体必须加括号；多语句宏必须使用 `do { ... } while (0)` 包裹。
- **〖强制〗** 宏参数禁止传入有副作用的表达式，如 `MAX(i++, j)`。

```c
#define USER_SERVICE_MAX(a, b) (((a) > (b)) ? (a) : (b))

#define USER_SERVICE_LOG_ERROR(message)          \
    do {                                         \
        log_write(LOG_LEVEL_ERROR, (message));   \
    } while (0)
```

## 23.3 内存与资源

- **〖强制〗** `malloc`、`calloc`、`realloc` 的返回值必须判空。
- **〖强制〗** `realloc` 结果必须先赋给临时变量，成功后再覆盖原指针，避免失败时内存泄漏。
- **〖强制〗** `free` 后立即将指针置为 `NULL`。
- **〖强制〗** 分配大小计算使用 `sizeof(*ptr)` 而非 `sizeof(type)`，并检查乘法溢出（或使用 `calloc`）。
- **〖强制〗** 禁止使用变长数组（VLA），可能导致栈溢出。
- **〖强制〗** 谁分配谁释放：模块必须提供配对的 `xxx_create()` / `xxx_destroy()` 接口。

## 23.4 错误处理

- **〖强制〗** 函数通过返回值返回错误码（统一定义的 `enum`），通过输出参数返回结果；返回错误码的函数调用方必须检查。
- **〖强制〗** 调用设置 `errno` 的系统函数后，必须立即检查并保存 `errno`。
- **〖推荐〗** 多资源清理允许使用 `goto` 跳转到函数末尾的统一清理标签，只允许向后跳转。

```c
user_service_status_t user_service_load(const char* path, user_list_t** out_list) {
    user_service_status_t status = USER_SERVICE_ERROR;
    FILE* file = NULL;
    user_list_t* list = NULL;

    file = fopen(path, "rb");
    if (file == NULL) {
        goto cleanup;
    }
    list = user_list_create();
    if (list == NULL) {
        goto cleanup;
    }
    /* 解析文件内容 */
    *out_list = list;
    list = NULL;   /* 所有权已转移给调用方 */
    status = USER_SERVICE_OK;

cleanup:
    user_list_destroy(list);
    if (file != NULL) {
        fclose(file);
    }
    return status;
}
```

## 23.5 与 C++ 互操作

- **〖强制〗** 供 C++ 调用的 C 头文件必须使用 `extern "C"` 包裹：

```c
#ifdef __cplusplus
extern "C" {
#endif

/* 函数声明 */

#ifdef __cplusplus
}
#endif
```

- **〖强制〗** C++ 实现的 `extern "C"` 接口内部必须捕获全部异常并转换为错误码，禁止异常穿越到 C 代码。

---

# 附录 A：工具配置样例 【补充】

## A.1 `.clang-format`

```yaml
BasedOnStyle: Google
Language: Cpp
Standard: c++20
IndentWidth: 4
ColumnLimit: 100
UseTab: Never
AccessModifierOffset: -4
DerivePointerAlignment: false
PointerAlignment: Left
AllowShortIfStatementsOnASingleLine: Never
AllowShortLoopsOnASingleLine: false
AllowShortFunctionsOnASingleLine: Inline
InsertBraces: true
SortIncludes: CaseSensitive
IncludeBlocks: Regroup
IncludeCategories:
  - Regex: '^<[a-z_]+\.h>$'          # C 系统头文件
    Priority: 2
  - Regex: '^<[a-z_]+>$'             # C++ 标准库
    Priority: 3
  - Regex: '^<.*>$'                  # 第三方库
    Priority: 4
  - Regex: '^".*"$'                  # 本项目
    Priority: 5
```

## A.2 `.clang-tidy`

```yaml
Checks: >
  -*,
  bugprone-*,
  cert-*,
  clang-analyzer-*,
  concurrency-*,
  cppcoreguidelines-*,
  misc-*,
  modernize-*,
  performance-*,
  readability-*,
  -modernize-use-trailing-return-type,
  -readability-identifier-length,
  -cppcoreguidelines-avoid-magic-numbers
WarningsAsErrors: 'bugprone-*,cert-*,clang-analyzer-*,concurrency-*'
CheckOptions:
  - { key: readability-identifier-naming.NamespaceCase,        value: lower_case }
  - { key: readability-identifier-naming.ClassCase,            value: CamelCase }
  - { key: readability-identifier-naming.StructCase,           value: CamelCase }
  - { key: readability-identifier-naming.EnumCase,             value: CamelCase }
  - { key: readability-identifier-naming.FunctionCase,         value: lower_case }
  - { key: readability-identifier-naming.VariableCase,         value: lower_case }
  - { key: readability-identifier-naming.ParameterCase,        value: lower_case }
  - { key: readability-identifier-naming.PrivateMemberCase,    value: lower_case }
  - { key: readability-identifier-naming.PrivateMemberSuffix,  value: _ }
  - { key: readability-identifier-naming.ConstexprVariableCase,   value: CamelCase }
  - { key: readability-identifier-naming.ConstexprVariablePrefix, value: k }
  - { key: readability-identifier-naming.EnumConstantCase,     value: CamelCase }
  - { key: readability-identifier-naming.EnumConstantPrefix,   value: k }
  - { key: readability-identifier-naming.MacroDefinitionCase,  value: UPPER_CASE }
  - { key: readability-identifier-naming.TemplateParameterCase, value: CamelCase }
  - { key: readability-function-cognitive-complexity.Threshold, value: 10 }
  - { key: readability-function-size.LineThreshold,            value: 50 }
  - { key: readability-function-size.ParameterThreshold,       value: 5 }
```

> 说明：`cppcoreguidelines-avoid-magic-numbers` 误报较多，关闭后由代码评审把关第 5 章的魔法值规则。

## A.3 CMake 警告与 Sanitizer 片段

```cmake
add_library(myproject_warnings INTERFACE)
target_compile_options(myproject_warnings INTERFACE
    $<$<CXX_COMPILER_ID:GNU,Clang>:
        -Wall -Wextra -Wpedantic -Werror
        -Wshadow -Wconversion -Wsign-conversion
        -Wnon-virtual-dtor -Wold-style-cast -Woverloaded-virtual
        -Wnull-dereference -Wformat=2>
    $<$<CXX_COMPILER_ID:MSVC>:/W4 /WX /permissive- /utf-8>
)

option(MYPROJECT_ENABLE_SANITIZERS "开启 ASan 与 UBSan" OFF)
if(MYPROJECT_ENABLE_SANITIZERS)
    target_compile_options(myproject_warnings INTERFACE
        -fsanitize=address,undefined -fno-omit-frame-pointer)
    target_link_options(myproject_warnings INTERFACE -fsanitize=address,undefined)
endif()

# 业务 target 链接该接口库即可继承全部选项
target_link_libraries(myproject_core PRIVATE myproject_warnings)
```

---

# 附录 B：Python 规范到 C/C++ 规范对照表 【补充】

| 原 Python 规范 | C/C++ 对应做法 |
| --- | --- |
| Ruff Format / Black | clang-format |
| Ruff / mypy / pyright | 编译器警告 `-Werror` + clang-tidy + cppcheck |
| `import` 分组 | `#include` 五组排序 + IWYU |
| `X \| None` | `std::optional<T>`、可空 `T*` |
| `Any` | `void*`、`std::any`（须说明原因） |
| `# type: ignore[code]` | `// NOLINT(check-name)`、`#pragma ... push/pop` |
| `enum.Enum` | `enum class` |
| `@dataclass(frozen=True)` | 聚合 `struct` + `const` / `= default` 比较 |
| `__eq__` 与 `__hash__` | `operator==` 与 `std::hash` 特化 |
| `__repr__` / `__str__` | `to_string()`、`operator<<`、`std::formatter` |
| `raise ... from e` | `std::throw_with_nested` |
| `except Exception: pass` | 空 `catch (...) {}`（禁止） |
| `logging` + `%s` 占位 | spdlog + `{}` 占位 |
| docstring（Google 风格） | Doxygen 注释 |
| `pytest` + `parametrize` | GoogleTest + `TEST_P` |
| `tmp_path` | `std::filesystem::temp_directory_path()` |
| `ThreadPoolExecutor` | 线程池 + `std::jthread` |
| `asyncio` | Boost.Asio + C++20 协程 |
| `yaml.safe_load` / `pickle` | 带校验的反序列化（Protobuf 等） |
| `pydantic-settings` | 启动时加载并校验的配置结构体 |
| `cProfile` / `py-spy` | perf / Callgrind / VTune / Google Benchmark |
| `pip-audit` / `bandit` | OSV-Scanner / CodeQL / clang-tidy `cert-*` |
| 无对应（GC 自动管理） | 第 9 章内存与资源管理、第 20 章未定义行为 |

---

# 附录 C：相对原规范的修订说明 【补充】

1. **新增章节**：第 0 章规范等级说明、第 9 章内存与资源管理、第 20 章未定义行为与可移植性、第 21 章构建与工程结构、第 23 章 C 语言专项、附录 A~C。
2. **新增小节**：1.3 命名空间、2.2 大括号与语句、4.2 const 正确性、4.3 auto、4.4 属性标注、8.1 Rule of 0/3/5、11.1 错误处理策略、11.4 断言、15.1 内存安全、15.2 编译加固。
3. **修正**：
   - 常量命名由“全大写”改为 `kUpperCamelCase`，避免与宏冲突（1.6）；
   - “注释必须使用中文”原在第 4 章（类型注解）与第 12 章重复，统一到第 13 章；
   - 原“192.1 分支策略”编号错误，改为 22.1；
   - 原第 7 章重试装饰器示例捕获所有 `Exception` 且丢弃最后一次异常，C++ 示例改为只捕获可重试的异常，最后一次失败的异常原样上抛；
   - 原 2.2 “顶层函数之间空两行”是 PEP 8 约定，C++ 中统一为空一行。
4. **删除或替换**：Python 特有条目（可变默认参数、`is None`、`__slots__`、`functools.wraps`、`TypeVar` 等）已替换为 C/C++ 中语义对应的规则，或在正文中说明不适用的原因。
