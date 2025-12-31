# git_push_all.py
import subprocess
import sys

def run_command(command):
    """Run a shell command and print its output."""
    try:
        result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True)
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e.cmd}")
        print(e.stdout)
        print(e.stderr)
        sys.exit(1)

def main():
    commit_message = input("Enter commit message: ").strip()
    if not commit_message:
        print("Commit message cannot be empty!")
        sys.exit(1)
    
    print("Staging all changes...")
    run_command("git add .")
    
    print("Committing changes...")
    run_command(f'git commit -m "{commit_message}"')
    
    print("Pushing to GitHub...")
    run_command("git push")
    
    print("✅ All changes pushed successfully!")

if __name__ == "__main__":
    main()
