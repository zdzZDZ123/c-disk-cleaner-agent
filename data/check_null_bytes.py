with open('data/database.py', 'rb') as f:
    content = f.read()
control_bytes = [b for b in content if b < 32 and b not in (9, 10, 13)]
print(f"控制字节（小于32且非Tab/换行/回车）数量: {len(control_bytes)}")
if control_bytes:
    print("控制字节的16进制值:", [hex(b) for b in control_bytes])
else:
    print("未检测到控制字节，文件为纯文本。") 