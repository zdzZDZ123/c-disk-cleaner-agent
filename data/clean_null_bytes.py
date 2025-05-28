# 用于清理 data/database.py 文件中的 null 字节
file_path = 'data/database.py'
with open(file_path, 'rb') as f:
    content = f.read()
cleaned = content.replace(b'\x00', b'')
with open(file_path, 'wb') as f:
    f.write(cleaned)
print(f"已清理 {file_path} 中的所有 null 字节。请重新运行你的主程序。") 