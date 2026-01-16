import sys
sys.path.append(r"c:\Users\Mateus\Desktop\ITEM\ItemManager\data")
try:
    import datspr
    print("Successfully imported datspr")
    # Verify UpgradeClassification exists in METADATA_FLAGS
    if 0x2F in datspr.METADATA_FLAGS:
        name, fmt = datspr.METADATA_FLAGS[0x2F]
        print(f"UpgradeClassification found: {name}, format: {fmt}")
        if name == "UpgradeClassification" and fmt == "<H":
            print("Verification Successful: UpgradeClassification flag is correct.")
        else:
             print("Verification Failed: Incorrect name or format.")
    else:
        print("Verification Failed: UpgradeClassification flag not found.")
except Exception as e:
    print(f"Verification Failed: {e}")
