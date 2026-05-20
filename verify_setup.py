#!/usr/bin/env python3
"""
Setup verification script for Meal Planner
Run this to check if everything is configured correctly
"""

import os
import sys
from pathlib import Path

def check_python_version():
    """Check if Python version is 3.9+"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 9):
        print("❌ Python 3.9+ is required")
        print(f"   Current version: {version.major}.{version.minor}.{version.micro}")
        return False
    print(f"✅ Python version: {version.major}.{version.minor}.{version.micro}")
    return True

def check_dependencies():
    """Check if required packages are installed"""
    required_packages = [
        'flask',
        'google.generativeai',
        'dotenv',
        'sqlalchemy'
    ]
    
    missing = []
    for package in required_packages:
        try:
            if package == 'dotenv':
                __import__('dotenv')
            elif package == 'google.generativeai':
                __import__('google.generativeai')
            else:
                __import__(package)
            print(f"✅ {package} is installed")
        except ImportError:
            print(f"❌ {package} is NOT installed")
            missing.append(package)
    
    if missing:
        print(f"\n⚠️  Missing packages: {', '.join(missing)}")
        print("   Run: pip install -r requirements.txt")
        return False
    return True

def check_env_file():
    """Check if .env file exists and has required keys"""
    env_path = Path('.env')
    
    if not env_path.exists():
        print("❌ .env file not found")
        print("   Create a .env file with GEMINI_API_KEY")
        return False
    
    print("✅ .env file exists")
    
    # Check for required keys (only API key needed)
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key or api_key == 'your_gemini_api_key_here':
        print("❌ GEMINI_API_KEY is not set or still has placeholder value")
        print("   Please add your Gemini API key to the .env file")
        return False
    
    print("✅ GEMINI_API_KEY is set")
    return True

def check_directories():
    """Check if required directories exist"""
    required_dirs = [
        'templates',
        'static/css',
        'static/js'
    ]
    
    all_exist = True
    for dir_path in required_dirs:
        if Path(dir_path).exists():
            print(f"✅ {dir_path}/ exists")
        else:
            print(f"❌ {dir_path}/ is missing")
            all_exist = False
    
    return all_exist

def check_files():
    """Check if required files exist"""
    required_files = [
        'app.py',
        'config.py',
        'models.py',
        'database.py',
        'gemini_service.py',
        'meal_planner.py',
        'ingredient_manager.py',
        'shopping_list.py',
        'requirements.txt',
        'templates/base.html',
        'templates/index.html',
        'static/css/style.css'
    ]
    
    all_exist = True
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"✅ {file_path} exists")
        else:
            print(f"❌ {file_path} is missing")
            all_exist = False
    
    return all_exist

def main():
    """Run all checks"""
    print("=" * 50)
    print("Meal Planner Setup Verification")
    print("=" * 50)
    print()
    
    checks = [
        ("Python Version", check_python_version),
        ("Dependencies", check_dependencies),
        (".env File", check_env_file),
        ("Directories", check_directories),
        ("Files", check_files)
    ]
    
    results = []
    for name, check_func in checks:
        print(f"\n📋 Checking {name}...")
        result = check_func()
        results.append((name, result))
    
    print("\n" + "=" * 50)
    print("Summary")
    print("=" * 50)
    
    all_passed = True
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
        if not result:
            all_passed = False
    
    print()
    if all_passed:
        print("🎉 All checks passed! You're ready to run the application.")
        print("\nTo start the app, run:")
        print("   python app.py")
    else:
        print("⚠️  Some checks failed. Please fix the issues above.")
        sys.exit(1)

if __name__ == '__main__':
    main()
