# Solana Wallet Generator

一个高效的 Solana 钱包生成器，支持生成特定前缀的钱包地址，使用多进程并行处理以提升生成速度。

## 功能特性

- ✅ 生成符合 Phantom 钱包标准的 Solana 钱包
- ✅ 支持筛选特定前缀的钱包地址（不区分大小写）
- ✅ 多进程并行处理，显著提升生成效率
- ✅ 自动内存管理和垃圾回收
- ✅ 实时进度显示和性能监控
- ✅ 将结果导出为 CSV 文件

## 系统要求

- Python 3.7+
- 支持多进程的操作系统（Windows/Linux/macOS）

## 安装依赖

```bash
pip install --upgrade bip-utils solders mnemonic
```

或者使用 requirements.txt：

```bash
pip install -r requirements.txt
```

### requirements.txt 内容：
```
bip-utils>=4.0.0
solders>=0.20.0
mnemonic>=0.20
```

## 使用方法

### 基本使用

```bash
python sol-w-generator.py
```

### 配置选项

在代码中修改以下配置参数：

```python
# --- 配置 ---
TARGET_COUNT = 1  # 目标生成数量
NUM_PROCESSES = 3  # 使用进程数
OUTPUT_FILENAME = 'sol-w-import.csv' # 输出文件名
MNEMONIC_LANGUAGE = 'english'
MNEMONIC_STRENGTH = 256 # 24 words
# The derivation path Phantom uses
DERIVATION_PATH = "m/44'/501'/0'/0'"

# ===== 新增配置选项 =====
# 选择生成模式：'lowercase', 'uppercase', 'custom'
GENERATION_MODE = 'custom'  # 可选: 'lowercase', 'uppercase', 'custom'

# 当GENERATION_MODE为'custom'时，使用下面的自定义前缀
CUSTOM_PREFIX = 'test'

# 当GENERATION_MODE为'lowercase'时，生成的前缀长度
LOWERCASE_PREFIX_LENGTH = 4  # 生成4位全小写字母开头

# 当GENERATION_MODE为'uppercase'时，生成的前缀长度  
UPPERCASE_PREFIX_LENGTH = 4  # 生成4位全大写字母开头
```

## 输出格式

生成的 CSV 文件包含两列：

| Address | Mnemonic |
|---------|----------|
| testXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX | word1 word2 word3 ... word24 |

## 性能说明

- **单进程模式**：约 2.4 秒生成 1000 个地址
- **双进程模式**：约 1.2 秒生成 1000 个地址
- **内存优化**：自动垃圾回收，避免长时间运行内存泄漏
- **生成速度**：三进程模式，约1小时生成一个前缀4字母不限大小写的地址

### 关于前缀匹配概率

由于 Solana 地址使用 Base58 编码，找到特定前缀的地址需要大量尝试：

- 1个字符前缀：平均需要 ~58 次尝试
- 2个字符前缀：平均需要 ~3,364 次尝试  
- 3个字符前缀：平均需要 ~195,112 次尝试
- 4个字符前缀：平均需要 ~11,316,496 次尝试

## 技术实现

### 钱包生成流程

1. **生成助记词**：使用 BIP39 标准生成 24 词助记词
2. **种子生成**：从助记词生成 BIP39 种子
3. **密钥派生**：使用 BIP32 SLIP-10 Ed25519 派生私钥
4. **地址生成**：通过 Solders 库生成 Solana 公钥地址

### 派生路径

使用 Phantom 钱包兼容的派生路径：`m/44'/501'/0'/0'`

### 多进程架构

- **工作进程**：独立生成钱包，找到匹配地址后放入队列
- **主进程**：收集结果，监控进度，管理进程生命周期
- **共享变量**：使用 multiprocessing.Value 安全地共享计数器

## 安全注意事项

⚠️ **重要提醒**：

1. **私钥安全**：生成的助记词具有完全的钱包控制权，请妥善保管
2. **测试用途**：建议仅用于测试目的，正式使用前请充分验证
3. **随机性**：确保在安全的环境中运行，避免随机数生成被预测
4. **备份**：及时备份生成的 CSV 文件

## 故障排除

### 常见错误

**ImportError: 缺少必要的库**
```bash
pip install --upgrade bip-utils solders mnemonic
```

**进程启动失败**
- Windows 用户：确保使用 Python 3.7+
- 某些系统可能需要设置 `multiprocessing.set_start_method('spawn')`

**生成速度慢**
- 增加 `NUM_PROCESSES` 数量（不超过 CPU 核心数）
- 降低目标前缀长度
- 检查系统资源使用情况

### 性能优化建议

1. **调整进程数**：设置为 CPU 核心数或稍少
2. **监控内存**：长时间运行时关注内存使用
3. **选择前缀**：避免过长的前缀以减少计算时间

## 开发指南

### 代码结构

```
sol-w-generator.py
├── 配置参数
├── generate_solana_wallet_from_mnemonic()  # 核心钱包生成函数
├── worker_process()                        # 工作进程函数
└── main()                                  # 主控制函数
```

### 自定义修改

如需自定义功能，可以修改：

- `TARGET_PREFIX`：更改目标前缀
- `DERIVATION_PATH`：更改派生路径（需了解 BIP32）
- `MNEMONIC_STRENGTH`：更改助记词长度（128=12词，256=24词）

## 许可证

本项目仅供学习和测试使用。使用者需自行承担使用风险。


**免责声明**：本工具生成的钱包地址和私钥仅供测试使用。在正式环境中使用前，请充分测试并确保安全性。作者不对因使用此工具造成的任何损失承担责任。
