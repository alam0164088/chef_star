#!/usr/bin/env python
import os
import sys

if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError:
        # Django not installed; provide helpful fallback
        print('Django not installed. Install from requirements.txt to use manage.py')
        sys.exit(1)
    execute_from_command_line(sys.argv)
