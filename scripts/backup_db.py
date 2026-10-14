from pathlib import Path
import sqlite3
root=Path('runtime');backup=root/'backups';backup.mkdir(exist_ok=True)
source=sqlite3.connect(root/'bsdt.sqlite3')
destination=sqlite3.connect(backup/'bsdt-before-v020.sqlite3')
source.backup(destination);destination.close();source.close()
print('SQLite backup saved')