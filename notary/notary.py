import hashlib
import os

LOG_FILE = "notary_log.txt"

def get_last_hash() -> str:
    """
    Reads the hash value of the last line of the log file
    If the file does not exist or is empty, the begining of the chain (Genesis) will return 64 0's
    """
    
    if not os.path.exists(LOG_FILE) or os.path.getsize(LOG_FILE) == 0:
        return "0" * 64

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
        if not lines:
            return "0" * 64
        last_line = lines[-1].strip()
        parts = last_line.rsplit(" | ", 1)
        if len(parts) == 2:
            return parts[1]

    return "0" * 64

def append_to_log(data: str) -> str:
    """
    Merge the data with the last hash and create SHA-256 chain
    and append it to bottom without deleting the file (Append-only)
    """

    # 1. Get the last hash value of the previous chain
    prev_hash = get_last_hash()

    # 2. Merge the data with the old hash and calculate the new SHA-256 value
    payload = f"{data}{prev_hash}".encode("utf-8")
    new_hash = hashlib.sha256(payload).hexdigest()

    # 3. Append to the file with the "a" (append) mode
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{data} | {new_hash}\n")

    return new_hash

def print_chain():
    """
    Reads the log file from head to tail and prints every line on the chain
    """

    if not os.path.exists(LOG_FILE) or os.path.getsize(LOG_FILE) == 0:
        print("\n[NOTARY] No logs to show \n")
        return

    print("\n=============== CRYPTOGRAPHIC NOTARY CHAIN ===============")
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for index, line in enumerate(f, start=1):
            parts = line.strip().split(" | ")
            if (len(parts) == 2):
                content, line_hash = parts
                print(f"[{index:02d}] Data: {content:<35} | Hash: {line_hash[:16]}...")
    print("=============================================================\n")

# Small Testing
if __name__ == "__main__":
    # Test 1
    """
    print("--- CHAIN TEST BEGINS ---")

    # Test 1: Adding first block (Should be written in the Genesis hash)
    h1 = append_to_log("System Started")
    print(f"1. Log Hash: {h1[:16]}...")

    # Test 2: Adding second block (Should be written in the h1 hash)
    h2 = append_to_log("Omers' Notary module activated")
    print(f"2. Log Hash: {h2[:16]}...")

    # Test 3: Final Check
    latest = get_last_hash()
    print(f"Last Read Hash: {latest[:16]}...")

    # Adding a new test data
    append_to_log("Omer notary print_chain fonksiyonunu test ediyor")
    
    # Print whole chain
    print_chain()

    if latest == h2:
        print("\n✅ TEST SUCCESS: Chain linked without breaking!")
    else:
        print("\n❌ TEST ERROR: Hash unmatched!")
    """

    """
    # Test 4: Manuel Control Block
    print("--- MANUEL ZERO CONTROL ---")
    append_to_log("First Block: Noter Module is Active")
    append_to_log("Second Block: Process Accepted")
    append_to_log("Third Block: Closing Done")
    """
    
    print_chain()
