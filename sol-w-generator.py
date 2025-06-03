import csv
import os
import time
import traceback
import multiprocessing
import gc
from multiprocessing import Process, Queue, Value
from solders.keypair import Keypair
from mnemonic import Mnemonic
# --- Corrected bip_utils Imports ---
# Import the specific class from the bip.bip32 submodule
from bip_utils.bip.bip32 import Bip32Slip10Ed25519
# Import the error class from the bip.bip44_base submodule
from bip_utils.bip.bip44_base import Bip44DepthError
# Bip39SeedGenerator is still needed and correctly imported from top level
from bip_utils import Bip39SeedGenerator
# --- End Corrected Imports ---

# --- 配置 ---
TARGET_COUNT = 2  # 目标生成2个"test"开头的钱包
NUM_PROCESSES = 3  # 使用两个核心
OUTPUT_FILENAME = 'sol-w-import.csv' # New filename
MNEMONIC_LANGUAGE = 'english'
MNEMONIC_STRENGTH = 256 # 24 words
# The derivation path Phantom uses
DERIVATION_PATH = "m/44'/501'/0'/0'"
TARGET_PREFIX = 'test'  # 目标前缀（不区分大小写）
# --- 结束配置 ---

def generate_solana_wallet_from_mnemonic():
    """
    Generates a Solana wallet address and its corresponding BIP39 mnemonic,
    using bip_utils.bip.bip32.Bip32Slip10Ed25519 to match Phantom wallet derivation.
    """
    try:
        # 1. Generate Mnemonic
        mnemo = Mnemonic(MNEMONIC_LANGUAGE)
        mnemonic_phrase = mnemo.generate(strength=MNEMONIC_STRENGTH)
        
        # 2. Generate BIP39 Seed from Mnemonic
        seed_bytes = Bip39SeedGenerator(mnemonic_phrase).Generate("") # Empty passphrase
        
        # 3. Derive the Private Key using Bip32Slip10Ed25519
        # Create a master key object from the seed using the specific class (now correctly imported)
        master_key = Bip32Slip10Ed25519.FromSeed(seed_bytes)
        
        # Derive the key for the specified path using the DerivePath method
        derived_key_ctx = master_key.DerivePath(DERIVATION_PATH)
        
        # Get the 32-byte private key from the derived context
        derived_private_key = derived_key_ctx.PrivateKey().Raw().ToBytes()
        
        # 4. Create Solana Keypair from the derived 32-byte private key
        keypair = Keypair.from_seed(derived_private_key)
        
        # 5. Get the public key (address)
        address = str(keypair.pubkey())
        
        return address, mnemonic_phrase
        
    except Bip44DepthError as e: # Bip44DepthError is now correctly imported
        print(f"\nError deriving path '{DERIVATION_PATH}': {e}")
        print("Please ensure the derivation path format is correct.")
        print(traceback.format_exc())
        return None, None
        
    except Exception as e:
        print(f"\nError generating single wallet:")
        print(traceback.format_exc())
        return None, None

def worker_process(process_id, result_queue, found_count, total_attempts):
    """
    工作进程函数，持续生成钱包直到主进程停止
    """
    local_attempts = 0
    
    while found_count.value < TARGET_COUNT:
        local_attempts += 1
        
        try:
            address, mnemonic_phrase = generate_solana_wallet_from_mnemonic()
            
            if address and mnemonic_phrase:
                # 检查地址是否以目标前缀开头（不区分大小写）
                if address.lower().startswith(TARGET_PREFIX.lower()):
                    # 使用锁确保原子操作
                    with found_count.get_lock():
                        if found_count.value < TARGET_COUNT:
                            found_count.value += 1
                            current_found = found_count.value
                            result_queue.put({'Address': address, 'Mnemonic': mnemonic_phrase})
                            print(f"进程 {process_id}: 找到第 {current_found} 个匹配的钱包: {address}")
            
            # 更新总尝试次数
            with total_attempts.get_lock():
                total_attempts.value += 1
                
        except Exception as e:
            print(f"进程 {process_id} 发生错误: {e}")
            continue
        
        # 每10000次尝试进行一次垃圾回收
        if local_attempts % 300000 == 0:
            gc.collect()
            if found_count.value >= TARGET_COUNT:
                break

def main():
    """
    主函数，使用多进程生成以"test"开头的钱包并将其保存到 CSV 文件。
    """
    print(f"开始使用 {NUM_PROCESSES} 个进程生成以'{TARGET_PREFIX}'开头的 Solana 钱包 (目标数量: {TARGET_COUNT})...")
    print(f"派生库: bip_utils.bip.bip32.Bip32Slip10Ed25519")
    print(f"派生路径: {DERIVATION_PATH} (Phantom 兼容)")
    
    start_time = time.time()
    
    # 创建共享变量和队列
    result_queue = Queue()
    found_count = Value('i', 0)  # 已找到的钱包数量
    total_attempts = Value('i', 0)  # 总尝试次数
    
    # 创建并启动工作进程
    processes = []
    for i in range(NUM_PROCESSES):
        p = Process(target=worker_process, args=(i+1, result_queue, found_count, total_attempts))
        p.start()
        processes.append(p)
    
    # 收集结果
    wallets_data = []
    last_report_time = start_time
    last_gc_time = start_time
    
    while len(wallets_data) < TARGET_COUNT:
        try:
            # 等待结果，设置超时避免无限等待
            wallet_data = result_queue.get(timeout=1)
            wallets_data.append(wallet_data)
        except:
            # 超时或其他异常，继续等待
            pass
        
        current_time = time.time()
        
        # 每30秒在主进程中也进行一次垃圾回收
        if current_time - last_gc_time >= 600:
            gc.collect()
            last_gc_time = current_time
        
        # 每5秒报告一次进度
        if current_time - last_report_time >= 30:
            elapsed_time = current_time - start_time
            current_attempts = total_attempts.value
            rate = current_attempts / elapsed_time if elapsed_time > 0 else 0
            print(f"进度: 已尝试 {current_attempts} 次 | "
                  f"找到: {len(wallets_data)}/{TARGET_COUNT} | "
                  f"耗时: {elapsed_time:.2f} 秒 | "
                  f"速率: {rate:.2f} 次/秒")
            last_report_time = current_time
    
    # 终止所有进程
    for p in processes:
        p.terminate()
        p.join()
    
    final_attempts = total_attempts.value
    print(f"\n成功找到 {TARGET_COUNT} 个以'{TARGET_PREFIX}'开头的钱包！")
    print(f"总共尝试了 {final_attempts} 次")
    
    if not wallets_data:
        print("未能生成任何钱包数据，无法写入 CSV 文件。")
        return
    
    print(f"\n开始将 {len(wallets_data)} 个钱包数据写入 {OUTPUT_FILENAME}...")
    write_start_time = time.time()
    saved_count = 0
    
    try:
        with open(OUTPUT_FILENAME, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['Address', 'Mnemonic']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(wallets_data)
            saved_count = len(wallets_data)
        
        write_elapsed_time = time.time() - write_start_time
        print(f"数据成功写入 {OUTPUT_FILENAME} (耗时: {write_elapsed_time:.2f} 秒)")
        
    except IOError as e:
        print(f"写入 CSV 文件时出错: {e}")
        print("请检查文件权限或路径是否正确。")
        
    except Exception as e:
        print(f"写入 CSV 时发生未知错误: {e}")
    
    total_time = time.time() - start_time
    print("\n--- 生成完成 ---")
    print(f"目标数量: {TARGET_COUNT} 个")
    print(f"成功生成并写入: {saved_count} 个")
    print(f"总尝试次数: {final_attempts} 次")  
    print(f"使用进程数: {NUM_PROCESSES} 个")
    
    if saved_count > 0:
        print(f"数据已保存到: {os.path.abspath(OUTPUT_FILENAME)}")
        print("\n生成的钱包地址:")
        for wallet in wallets_data:
            print(f"  {wallet['Address']}")
    
    print(f"总耗时: {total_time:.2f} 秒")

if __name__ == "__main__":
    # Installation check - verify the deeper import paths work
    try:
        import solders
        import mnemonic
        import bip_utils
        # Verify specific class imports from sub-submodules
        from bip_utils.bip.bip32 import Bip32Slip10Ed25519
        from bip_utils.bip.bip44_base import Bip44DepthError
    except ImportError as e:
        print(f"错误：缺少必要的库或子模块无法访问 ({e})。请确保已安装最新版本:")
        print("python3 -m pip install --upgrade bip-utils solders mnemonic")
        exit(1)
    
    # 设置多进程启动方法（Windows兼容性）
    multiprocessing.set_start_method('spawn', force=True)
    
    main()