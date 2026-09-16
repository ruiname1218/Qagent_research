"""Public entry point for the three reported conditions."""
import sys

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print('Usage: python -m qagent {oneshot,feedback,restart} [options]')
        return
    if sys.argv[1] == 'restart':
        del sys.argv[1]
        from .restart import main as run
    else:
        from .baselines import main as run
    run()

if __name__ == '__main__':
    main()
