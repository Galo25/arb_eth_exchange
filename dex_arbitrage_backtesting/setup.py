#!/usr/bin/env python3
"""
Setup script for DEX Arbitrage Backtesting System

This script initializes the database and creates the necessary folder structure.
"""

import os
import sys
from pathlib import Path

def create_project_structure():
    """Create the project folder structure"""
    folders = [
        'database',
        'fetcher',
        'parser',
        'analyzer',
        'scripts',
        'logs',
        'data',
        'reports'
    ]
    
    for folder in folders:
        Path(folder).mkdir(exist_ok=True)
        print(f"✅ Created folder: {folder}")

def create_init_files():
    """Create __init__.py files for Python packages"""
    init_folders = ['database', 'fetcher', 'parser', 'analyzer']
    
    for folder in init_folders:
        init_file = Path(folder) / '__init__.py'
        if not init_file.exists():
            init_file.touch()
            print(f"✅ Created: {folder}/__init__.py")

def setup_environment():
    """Setup environment variables"""
    env_file = Path('.env')
    env_example = Path('env_example.txt')
    
    if not env_file.exists() and env_example.exists():
        # Copy example to .env
        with open(env_example, 'r') as f:
            content = f.read()
        
        with open('.env', 'w') as f:
            f.write(content)
        
        print("✅ Created .env file from env_example.txt")
        print("⚠️  Please update ETHERSCAN_API_KEY in .env file")
    elif env_file.exists():
        print("✅ .env file already exists")
    else:
        print("⚠️  No environment configuration found")

def install_dependencies():
    """Install required Python packages"""
    print("📦 Installing dependencies...")
    
    try:
        import subprocess
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
        print("✅ Dependencies installed successfully")
    except subprocess.CalledProcessError:
        print("❌ Failed to install dependencies")
        print("Please run: pip install -r requirements.txt")

def setup_database():
    """Initialize the database"""
    print("🗄️  Setting up database...")
    
    try:
        from database.schema import create_database
        engine = create_database()
        print("✅ Database initialized successfully")
        return engine
    except Exception as e:
        print(f"❌ Database setup failed: {e}")
        return None

def main():
    """Main setup function"""
    print("🚀 Setting up DEX Arbitrage Backtesting System")
    print("=" * 50)
    
    # Create project structure
    create_project_structure()
    
    # Create init files
    create_init_files()
    
    # Setup environment
    setup_environment()
    
    # Install dependencies
    install_dependencies()
    
    # Setup database
    engine = setup_database()
    
    print("\n" + "=" * 50)
    if engine:
        print("✅ Setup completed successfully!")
        print("\n🎯 Next steps:")
        print("1. Update ETHERSCAN_API_KEY in .env file")
        print("2. Run: python scripts/fetch_etherscan_data.py --setup-db --start-block 18000000 --end-block 18000100")
        print("3. Check the README.md for detailed usage instructions")
    else:
        print("❌ Setup completed with errors")
        print("Please check the error messages above")

if __name__ == "__main__":
    main()
