"""
Модуль для асинхронной работы с SQLite.
Использует встроенный sqlite3 с asyncio для потокобезопасности.
"""

import sqlite3
import asyncio
import logging
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class Database:
    """Асинхронный менеджер базы данных"""
    
    def __init__(self, db_path: str = 'bot_database.sqlite'):
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self._connection: Optional[sqlite3.Connection] = None
        self._executor = ThreadPoolExecutor(max_workers=3)
    
    async def initialize(self):
        """Инициализация базы данных и создание таблиц"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._executor, self._create_connection)
        await self._create_tables()
        logger.info("База данных готова к работе")
    
    def _create_connection(self):
        """Создание соединения с БД"""
        self._connection = sqlite3.connect(
            self.db_path, 
            check_same_thread=False,
            isolation_level=None
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._connection.execute("PRAGMA cache_size=10000")
    
    async def _run_in_thread(self, func, *args, **kwargs):
        """Выполнение функции в отдельном потоке"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: func(*args, **kwargs)
        )
    
    async def _create_tables(self):
        """Создание всех необходимых таблиц"""
        async with self._lock:
            def _create():
                self._connection.executescript('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER,
                        group_id INTEGER,
                        username TEXT,
                        first_name TEXT,
                        status TEXT DEFAULT 'pending',
                        attempts INTEGER DEFAULT 0,
                        join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        verification_date TIMESTAMP,
                        PRIMARY KEY (user_id, group_id)
                    );
                    
                    CREATE TABLE IF NOT EXISTS statistics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        group_id INTEGER NOT NULL,
                        total_joined INTEGER DEFAULT 0,
                        passed INTEGER DEFAULT 0,
                        failed INTEGER DEFAULT 0,
                        date DATE NOT NULL DEFAULT (date('now')),
                        UNIQUE(group_id, date)
                    );
                    
                    CREATE TABLE IF NOT EXISTS verification_messages (
                        user_id INTEGER,
                        group_id INTEGER,
                        message_id INTEGER,
                        correct_answer INTEGER,
                        attempts INTEGER DEFAULT 0,
                        PRIMARY KEY (user_id, group_id)
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
                    CREATE INDEX IF NOT EXISTS idx_users_group ON users(group_id);
                    CREATE INDEX IF NOT EXISTS idx_stats_group ON statistics(group_id);
                    CREATE INDEX IF NOT EXISTS idx_stats_date ON statistics(date);
                ''')
                self._connection.commit()
            
            await self._run_in_thread(_create)
    
    async def add_user(self, user_id: int, group_id: int, 
                       username: str = None, first_name: str = None) -> bool:
        """Добавление нового пользователя"""
        async with self._lock:
            def _add():
                try:
                    cursor = self._connection.execute(
                        '''INSERT OR IGNORE INTO users 
                           (user_id, group_id, username, first_name) 
                           VALUES (?, ?, ?, ?)''',
                        (user_id, group_id, username, first_name)
                    )
                    
                    if cursor.rowcount > 0:
                        today = self._connection.execute("SELECT date('now')").fetchone()[0]
                        
                        self._connection.execute(
                            '''INSERT INTO statistics (group_id, total_joined, date) 
                               VALUES (?, 1, ?)
                               ON CONFLICT(group_id, date) DO UPDATE 
                               SET total_joined = total_joined + 1''',
                            (group_id, today)
                        )
                        self._connection.commit()
                    return True
                except Exception as e:
                    logger.error(f"Ошибка при добавлении пользователя: {e}")
                    return False
            
            return await self._run_in_thread(_add)
    
    async def update_user_status(self, user_id: int, group_id: int, 
                                 status: str) -> bool:
        """Обновление статуса пользователя"""
        async with self._lock:
            def _update():
                try:
                    self._connection.execute(
                        '''UPDATE users 
                           SET status = ?, verification_date = datetime('now') 
                           WHERE user_id = ? AND group_id = ?''',
                        (status, user_id, group_id)
                    )
                    
                    today = self._connection.execute("SELECT date('now')").fetchone()[0]
                    stat_field = 'passed' if status == 'passed' else 'failed'
                    
                    self._connection.execute(
                        f'''INSERT INTO statistics (group_id, {stat_field}, date) 
                           VALUES (?, 1, ?)
                           ON CONFLICT(group_id, date) DO UPDATE 
                           SET {stat_field} = {stat_field} + 1''',
                        (group_id, today)
                    )
                    
                    self._connection.commit()
                    return True
                except Exception as e:
                    logger.error(f"Ошибка при обновлении статуса: {e}")
                    return False
            
            return await self._run_in_thread(_update)
    
    async def increment_attempts(self, user_id: int, group_id: int) -> int:
        """Увеличение счетчика попыток"""
        async with self._lock:
            def _increment():
                self._connection.execute(
                    'UPDATE users SET attempts = attempts + 1 WHERE user_id = ? AND group_id = ?',
                    (user_id, group_id)
                )
                self._connection.commit()
                
                cursor = self._connection.execute(
                    'SELECT attempts FROM users WHERE user_id = ? AND group_id = ?',
                    (user_id, group_id)
                )
                row = cursor.fetchone()
                return row[0] if row else 0
            
            return await self._run_in_thread(_increment)
    
    async def get_user(self, user_id: int, group_id: int) -> Optional[Dict]:
        """Получение информации о пользователе"""
        def _get():
            cursor = self._connection.execute(
                'SELECT * FROM users WHERE user_id = ? AND group_id = ?',
                (user_id, group_id)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        
        return await self._run_in_thread(_get)
    
    async def remove_verification(self, user_id: int, group_id: int):
        """Удаление данных о проверке"""
        async with self._lock:
            def _remove():
                self._connection.execute(
                    'DELETE FROM users WHERE user_id = ? AND group_id = ?',
                    (user_id, group_id)
                )
                self._connection.execute(
                    'DELETE FROM verification_messages WHERE user_id = ? AND group_id = ?',
                    (user_id, group_id)
                )
                self._connection.commit()
            
            await self._run_in_thread(_remove)
    
    async def save_verification_message(self, user_id: int, group_id: int,
                                       message_id: int, correct_answer: int):
        """Сохранение сообщения проверки"""
        async with self._lock:
            def _save():
                self._connection.execute(
                    '''INSERT OR REPLACE INTO verification_messages 
                       (user_id, group_id, message_id, correct_answer) 
                       VALUES (?, ?, ?, ?)''',
                    (user_id, group_id, message_id, correct_answer)
                )
                self._connection.commit()
            
            await self._run_in_thread(_save)
    
    async def get_verification_message(self, user_id: int, 
                                      group_id: int) -> Optional[Dict]:
        """Получение данных о сообщении проверки"""
        def _get():
            cursor = self._connection.execute(
                'SELECT * FROM verification_messages WHERE user_id = ? AND group_id = ?',
                (user_id, group_id)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        
        return await self._run_in_thread(_get)
    
    async def get_statistics(self, group_id: int, 
                            period: str = 'all') -> Dict[str, Any]:
        """Получение статистики по группе"""
        def _get():
            if period == 'today':
                date_filter = "AND date = date('now')"
            elif period == 'yesterday':
                date_filter = "AND date = date('now', '-1 day')"
            elif period == '7days':
                date_filter = "AND date >= date('now', '-7 days')"
            elif period == '30days':
                date_filter = "AND date >= date('now', '-30 days')"
            else:
                date_filter = ""
            
            query = f'''
                SELECT 
                    COALESCE(SUM(total_joined), 0) as total_joined,
                    COALESCE(SUM(passed), 0) as passed,
                    COALESCE(SUM(failed), 0) as failed
                FROM statistics 
                WHERE group_id = ? {date_filter}
            '''
            
            cursor = self._connection.execute(query, (group_id,))
            stats = cursor.fetchone()
            
            total = stats[0]
            passed = stats[1]
            failed = stats[2]
            
            return {
                'total': total,
                'passed': passed,
                'failed': failed,
                'pending': total - passed - failed if total > 0 else 0,
                'success_rate': round((passed / total * 100), 2) if total > 0 else 0
            }
        
        return await self._run_in_thread(_get)
    
    async def get_users_by_group(self, group_id: int, 
                                 period: str = 'all') -> List[Dict]:
        """Получение списка пользователей группы"""
        def _get():
            if period == 'today':
                date_filter = "AND date(join_date) = date('now')"
            elif period == 'yesterday':
                date_filter = "AND date(join_date) = date('now', '-1 day')"
            elif period == '7days':
                date_filter = "AND join_date >= datetime('now', '-7 days')"
            elif period == '30days':
                date_filter = "AND join_date >= datetime('now', '-30 days')"
            else:
                date_filter = ""
            
            query = f'''
                SELECT * FROM users 
                WHERE group_id = ? {date_filter}
                ORDER BY join_date DESC
            '''
            
            cursor = self._connection.execute(query, (group_id,))
            return [dict(row) for row in cursor.fetchall()]
        
        return await self._run_in_thread(_get)
    
    async def get_all_groups(self) -> List[int]:
        """Получение списка всех групп"""
        def _get():
            cursor = self._connection.execute(
                'SELECT DISTINCT group_id FROM users UNION SELECT DISTINCT group_id FROM statistics'
            )
            return [row[0] for row in cursor.fetchall()]
        
        return await self._run_in_thread(_get)
    
    async def close(self):
        """Закрытие соединения с базой данных"""
        if self._connection:
            def _close():
                try:
                    self._connection.commit()
                    self._connection.close()
                except Exception:
                    pass
            
            await self._run_in_thread(_close)
        
        self._executor.shutdown(wait=True)
        logger.info("Соединение с БД закрыто")