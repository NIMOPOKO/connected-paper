import subprocess
import sys
import os

if __name__ == "__main__":
    # カレントディレクトリを app.py がある場所に移動（必要なら）
    os.chdir(os.path.dirname(__file__))
    # Streamlit をモジュールとして起動
    subprocess.call([sys.executable, "-m", "streamlit", "run", "app.py"])