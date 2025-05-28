print("--- clean_null_bytes_recursive.py starting ---")
import os
import glob

def clean_file(file_path):
    print(f"--- Processing file: {file_path} ---")
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        # print(f"--- Read {len(content)} bytes from {file_path} ---")
        
        cleaned_content = content.replace(b'\x00', b'')
        
        if content == cleaned_content:
            print(f"No null bytes found in {file_path}.")
        else:
            print(f"!!! Null bytes FOUND in {file_path}. Original size: {len(content)}, Cleaned size: {len(cleaned_content)} !!!")
            with open(file_path, 'wb') as f:
                f.write(cleaned_content)
            print(f"Successfully removed null bytes from {file_path}.")
            return True # Indicates a change was made
            
    except Exception as e:
        print(f"Error processing file {file_path}: {e}")
    return False # Indicates no change or error

def clean_directory(directory_path):
    print(f"--- Scanning directory: {directory_path} ---")
    cleaned_any_file = False
    for filepath in glob.glob(os.path.join(directory_path, '**', '*.py'), recursive=True):
        if os.path.isfile(filepath):
            if clean_file(filepath):
                cleaned_any_file = True
    if not cleaned_any_file:
        print(f"--- No files needed cleaning in {directory_path} ---")
    else:
        print(f"--- Finished cleaning files in {directory_path}. Some files were modified. ---")

if __name__ == "__main__":
    print("--- clean_null_bytes_recursive.py __main__ block ---")
    
    # Define absolute paths to the directories to scan
    # Assuming this script is in d:\c_disk_cleaner_agent\data\
    base_project_dir = r"d:\c_disk_cleaner_agent"
    data_dir = os.path.join(base_project_dir, 'data')
    services_dir = os.path.join(base_project_dir, 'services')
    core_dir = os.path.join(base_project_dir, 'core') # Added core as it's also part of the app
    config_dir = os.path.join(base_project_dir, 'config') # Added config
    app_file = os.path.join(base_project_dir, 'app.py')

    dirs_to_clean = []
    if os.path.isdir(data_dir):
        dirs_to_clean.append(data_dir)
    else:
        print(f"Warning: Data directory not found: {data_dir}")
        
    if os.path.isdir(services_dir):
        dirs_to_clean.append(services_dir)
    else:
        print(f"Warning: Services directory not found: {services_dir}")

    if os.path.isdir(core_dir):
        dirs_to_clean.append(core_dir)
    else:
        print(f"Warning: Core directory not found: {core_dir}")

    if os.path.isdir(config_dir):
        dirs_to_clean.append(config_dir)
    else:
        print(f"Warning: Config directory not found: {config_dir}")

    if not dirs_to_clean and not os.path.isfile(app_file):
        print("CRITICAL ERROR: No valid directories or app.py found to clean.")
        exit(1)

    for target_dir in dirs_to_clean:
        print(f"Attempting to clean directory: {target_dir}")
        clean_directory(target_dir)
        
    # Clean app.py specifically
    if os.path.isfile(app_file):
        print(f"Attempting to clean app file: {app_file}")
        clean_file(app_file)
    else:
        print(f"Warning: app.py not found at {app_file}")

    print("--- clean_null_bytes_recursive.py finished ---")