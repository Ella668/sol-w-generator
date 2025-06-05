import csv
import os
import time
import traceback
import multiprocessing
import gc
from multiprocessing import Process, Queue, Value, shared_memory
from solders.keypair import Keypair
from mnemonic import Mnemonic
# --- Corrected bip_utils Imports ---
from bip_utils.bip.bip32 import Bip32Slip10Ed25519
from bip_utils.bip.bip44_base import Bip44DepthError
from bip_utils import Bip39SeedGenerator
# --- End Corrected Imports ---

# --- 配置 ---
TARGET_COUNT = 1  # 目标生成数量
# 动态调整进程数：使用CPU核心数但限制最大值
NUM_PROCESSES = min(multiprocessing.cpu_count(), 8)  # 最多8个进程
OUTPUT_FILENAME = 'sol-w-import.csv' # 输出文件名
MNEMONIC_LANGUAGE = 'english'
MNEMONIC_STRENGTH = 256 # 24 words
DERIVATION_PATH = "m/44'/501'/0'/0'"

# ===== 新增配置选项 =====
GENERATION_MODE = 'custom'  # 可选: 'lowercase', 'uppercase', 'custom'
CUSTOM_PREFIX = 'test' # 把 test 改成你想生成的地址前缀
LOWERCASE_PREFIX_LENGTH = 4  
UPPERCASE_PREFIX_LENGTH = 4  
# ===== 配置结束 =====

# 预编译正则表达式和常量
import re
if GENERATION_MODE == 'lowercase':
    LOWERCASE_PATTERN = re.compile(r'^[a-z]{' + str(LOWERCASE_PREFIX_LENGTH) + r'}')
elif GENERATION_MODE == 'uppercase':
    UPPERCASE_PATTERN = re.compile(r'^[A-Z]{' + str(UPPERCASE_PREFIX_LENGTH) + r'}')
elif GENERATION_MODE == 'custom':
    CUSTOM_PREFIX_LOWER = CUSTOM_PREFIX.lower()
    CUSTOM_PREFIX_LEN = len(CUSTOM_PREFIX)

def check_address_match_optimized(address):
    """
    优化的地址匹配检查，使用预编译的模式
    """
    if GENERATION_MODE == 'lowercase':
        return bool(LOWERCASE_PATTERN.match(address))
    elif GENERATION_MODE == 'uppercase':
        return bool(UPPERCASE_PATTERN.match(address))
    elif GENERATION_MODE == 'custom':
        # 直接比较前缀，避免创建新字符串
        return (len(address) >= CUSTOM_PREFIX_LEN and 
                address[:CUSTOM_PREFIX_LEN].lower() == CUSTOM_PREFIX_LOWER)
    return False

def get_target_description():
    """获取目标描述文本"""
    if GENERATION_MODE == 'lowercase':
        return f"前{LOWERCASE_PREFIX_LENGTH}位全小写字母"
    elif GENERATION_MODE == 'uppercase':
        return f"前{UPPERCASE_PREFIX_LENGTH}位全大写字母"
    elif GENERATION_MODE == 'custom':
        return f"以'{CUSTOM_PREFIX}'开头"
    else:
        return "未知条件"

class WalletGenerator:
    """钱包生成器类，减少重复初始化开销"""
    
    def __init__(self):
        self.mnemo = Mnemonic(MNEMONIC_LANGUAGE)
        # 预解析派生路径
        self.derivation_path = DERIVATION_PATH
    
    def generate_wallet(self):
        """
        优化的钱包生成方法
        """
        try:
            # 1. 生成助记词
            mnemonic_phrase = self.mnemo.generate(strength=MNEMONIC_STRENGTH)
            
            # 2. 生成种子
            seed_bytes = Bip39SeedGenerator(mnemonic_phrase).Generate("")
            
            # 3. 派生私钥
            master_key = Bip32Slip10Ed25519.FromSeed(seed_bytes)
            derived_key_ctx = master_key.DerivePath(self.derivation_path)
            derived_private_key = derived_key_ctx.PrivateKey().Raw().ToBytes()
            
            # 4. 创建Solana密钥对
            keypair = Keypair.from_seed(derived_private_key)
            address = str(keypair.pubkey())
            
            return address, mnemonic_phrase
            
        except Exception as e:
            return None, None

def worker_process_optimized(process_id, result_queue, found_count, total_attempts):
    """
    优化的工作进程函数
    """
    # 每个进程创建自己的生成器实例
    generator = WalletGenerator()
    local_attempts = 0
    local_found = 0
    batch_size = 1000  # 批量更新计数器
    
    print(f"进程 {process_id} 启动")
    
    while True:
        # 批量检查是否达到目标
        if local_attempts % batch_size == 0:
            with found_count.get_lock():
                if found_count.value >= TARGET_COUNT:
                    break
        
        local_attempts += 1
        
        try:
            address, mnemonic_phrase = generator.generate_wallet()
            
            if address and mnemonic_phrase:
                if check_address_match_optimized(address):
                    # 使用锁确保原子操作
                    with found_count.get_lock():
                        if found_count.value < TARGET_COUNT:
                            found_count.value += 1
                            current_found = found_count.value
                            local_found += 1
                            result_queue.put({
                                'Address': address, 
                                'Mnemonic': mnemonic_phrase,
                                'Process': process_id
                            })
                            print(f"🎯 进程 {process_id}: 找到第 {current_found} 个匹配钱包: {address}")
                            
                            if current_found >= TARGET_COUNT:
                                break
            
        except Exception as e:
            continue
        
        # 批量更新总尝试次数，减少锁竞争
        if local_attempts % batch_size == 0:
            with total_attempts.get_lock():
                total_attempts.value += local_attempts
                local_attempts = 0
        
        # 定期垃圾回收，但频率降低
        if (local_attempts + local_found * batch_size) % 500000 == 0:
            gc.collect()
    
    # 最终更新剩余的尝试次数
    if local_attempts > 0:
        with total_attempts.get_lock():
            total_attempts.value += local_attempts
    
    print(f"进程 {process_id} 完成，本地找到: {local_found} 个")

def monitor_progress(start_time, total_attempts, found_count, target_count):
    """独立的进度监控函数"""
    last_attempts = 0
    last_time = start_time
    
    while found_count.value < target_count:
        time.sleep(10)  # 每10秒报告一次
        
        current_time = time.time()
        current_attempts = total_attempts.value
        elapsed_time = current_time - start_time
        
        # 计算速率
        attempts_diff = current_attempts - last_attempts
        time_diff = current_time - last_time
        current_rate = attempts_diff / time_diff if time_diff > 0 else 0
        overall_rate = current_attempts / elapsed_time if elapsed_time > 0 else 0
        
        print(f"📊 进度报告: 尝试 {current_attempts:,} 次 | "
              f"找到 {found_count.value}/{target_count} | "
              f"用时 {elapsed_time:.1f}s | "
              f"当前速率: {current_rate:.0f}/s | "
              f"平均速率: {overall_rate:.0f}/s")
        
        last_attempts = current_attempts
        last_time = current_time
        
        if found_count.value >= target_count:
            break

def main():
    """优化的主函数"""
    target_desc = get_target_description()
    print(f"🚀 启动优化版 Solana 钱包生成器")
    print(f"📋 配置信息:")
    print(f"   - 目标条件: {target_desc}")
    print(f"   - 目标数量: {TARGET_COUNT}")
    print(f"   - 使用进程: {NUM_PROCESSES} 个 (CPU核心: {multiprocessing.cpu_count()})")
    print(f"   - 生成模式: {GENERATION_MODE}")
    print(f"   - 派生路径: {DERIVATION_PATH}")
    print(f"   - 输出文件: {OUTPUT_FILENAME}")
    
    start_time = time.time()
    
    # 创建共享变量和队列
    result_queue = Queue(maxsize=100)  # 限制队列大小
    found_count = Value('i', 0)
    total_attempts = Value('i', 0)
    
    # 创建并启动工作进程
    processes = []
    for i in range(NUM_PROCESSES):
        p = Process(
            target=worker_process_optimized, 
            args=(i+1, result_queue, found_count, total_attempts)
        )
        p.start()
        processes.append(p)
    
    # 启动进度监控进程
    monitor_process = Process(
        target=monitor_progress,
        args=(start_time, total_attempts, found_count, TARGET_COUNT)
    )
    monitor_process.start()
    
    # 收集结果
    wallets_data = []
    timeout_count = 0
    max_timeout = 5  # 最大超时次数
    
    print(f"⏳ 开始生成钱包...")
    
    while len(wallets_data) < TARGET_COUNT:
        try:
            wallet_data = result_queue.get(timeout=2)
            wallets_data.append(wallet_data)
            timeout_count = 0  # 重置超时计数
            
            # 显示找到的钱包
            print(f"✅ 收集到钱包 {len(wallets_data)}/{TARGET_COUNT}: {wallet_data['Address']}")
            
        except:
            timeout_count += 1
            if timeout_count >= max_timeout:
                # 检查进程是否都还活着
                alive_processes = [p for p in processes if p.is_alive()]
                if not alive_processes:
                    print("⚠️  所有工作进程已结束，但未达到目标数量")
                    break
                timeout_count = 0
            continue
    
    # 清理进程
    print("🛑 停止所有进程...")
    monitor_process.terminate()
    
    for p in processes:
        p.terminate()
        p.join(timeout=2)
        if p.is_alive():
            p.kill()  # 强制终止
    
    monitor_process.join(timeout=2)
    if monitor_process.is_alive():
        monitor_process.kill()
    
    # 最终统计
    final_attempts = total_attempts.value
    total_time = time.time() - start_time
    success_count = len(wallets_data)
    
    print(f"\n🎉 生成完成!")
    print(f"📊 最终统计:")
    print(f"   - 成功生成: {success_count}/{TARGET_COUNT} 个钱包")
    print(f"   - 总尝试次数: {final_attempts:,} 次")
    print(f"   - 总耗时: {total_time:.2f} 秒")
    print(f"   - 平均速率: {final_attempts/total_time:.0f} 次/秒")
    
    if success_count > 0:
        success_rate = success_count / final_attempts * 100 if final_attempts > 0 else 0
        print(f"   - 成功率: {success_rate:.8f}%")
    
    if not wallets_data:
        print("❌ 未生成任何钱包数据")
        return
    
    # 写入CSV文件
    print(f"\n💾 保存数据到 {OUTPUT_FILENAME}...")
    write_start_time = time.time()
    
    try:
        with open(OUTPUT_FILENAME, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['Address', 'Mnemonic']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for wallet in wallets_data:
                writer.writerow({
                    'Address': wallet['Address'],
                    'Mnemonic': wallet['Mnemonic']
                })
        
        write_time = time.time() - write_start_time
        file_path = os.path.abspath(OUTPUT_FILENAME)
        
        print(f"✅ 数据保存成功!")
        print(f"   - 文件路径: {file_path}")
        print(f"   - 保存耗时: {write_time:.2f} 秒")
        print(f"   - 钱包数量: {len(wallets_data)} 个")
        
        print(f"\n🔑 生成的钱包地址:")
        for i, wallet in enumerate(wallets_data, 1):
            print(f"   {i}. {wallet['Address']}")
        
    except Exception as e:
        print(f"❌ 保存文件时出错: {e}")

if __name__ == "__main__":
    # 安装检查
    try:
        import solders
        import mnemonic
        import bip_utils
        from bip_utils.bip.bip32 import Bip32Slip10Ed25519
        from bip_utils.bip.bip44_base import Bip44DepthError
    except ImportError as e:
        print(f"❌ 缺少必要的库: {e}")
        print("请运行: python3 -m pip install --upgrade bip-utils solders mnemonic")
        exit(1)
    
    # 设置多进程启动方法
    if hasattr(multiprocessing, 'set_start_method'):
        try:
            multiprocessing.set_start_method('fork', force=True)  # macOS上fork更快
        except RuntimeError:
            multiprocessing.set_start_method('spawn', force=True)  # 备选方案
    
    main()
