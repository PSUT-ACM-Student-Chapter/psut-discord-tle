import os
import asyncio
import logging
import sqlite3
import discord
from discord.ext import commands

class Todo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Initialize DB directly with native sqlite3
        os.makedirs('data', exist_ok=True)
        self.db_conn = sqlite3.connect('data/todo.db', check_same_thread=False)
        self._init_db()

    def _init_db(self):
        """Initializes the isolated TODO database."""
        cursor = self.db_conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_todo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                task TEXT NOT NULL,
                deadline TEXT,
                status INTEGER DEFAULT 0
            )
        ''')
        self.db_conn.commit()
        self.logger.info("TODO Database initialized successfully.")

    def cog_unload(self):
        """Clean up the database connection when unloaded."""
        if self.db_conn:
            self.db_conn.close()

    @commands.group(invoke_without_command=True, aliases=['todos'])
    async def todo(self, ctx):
        """Manage your personal TODO list."""
        await ctx.send_help(ctx.command)

    @todo.command(name='add')
    async def todo_add(self, ctx, *, task_and_deadline: str):
        """Add a task. Use | to separate task and deadline.
        Example: ;todo add Finish assignment | Tomorrow 5 PM
        """
        parts = task_and_deadline.split('|', 1)
        task = parts[0].strip()
        deadline = parts[1].strip() if len(parts) > 1 else None
        
        cursor = self.db_conn.cursor()
        cursor.execute(
            'INSERT INTO user_todo (user_id, task, deadline, status) VALUES (?, ?, ?, 0)',
            (ctx.author.id, task, deadline)
        )
        self.db_conn.commit()
            
        msg = f"✅ Task added: **{task}**"
        if deadline:
            msg += f" *(Deadline: {deadline})*"
        await ctx.send(msg)

    @todo.command(name='remove', aliases=['delete', 'rm'])
    async def todo_remove(self, ctx, task_id: int):
        """Remove a task from your list by its ID."""
        cursor = self.db_conn.cursor()
        cursor.execute(
            'DELETE FROM user_todo WHERE id = ? AND user_id = ?',
            (task_id, ctx.author.id)
        )
        if cursor.rowcount == 0:
            return await ctx.send("❌ Task not found or you don't have permission to delete it.")
        self.db_conn.commit()
        await ctx.send(f"✅ Task #{task_id} removed successfully.")

    @todo.command(name='check', aliases=['done'])
    async def todo_check(self, ctx, task_id: int):
        """Manually mark a task as completed using its ID."""
        cursor = self.db_conn.cursor()
        cursor.execute(
            'UPDATE user_todo SET status = 1 WHERE id = ? AND user_id = ?',
            (task_id, ctx.author.id)
        )
        if cursor.rowcount == 0:
            return await ctx.send("❌ Task not found.")
        self.db_conn.commit()
        await ctx.send(f"✅ Task #{task_id} marked as completed!")

    @todo.command(name='uncheck')
    async def todo_uncheck(self, ctx, task_id: int):
        """Manually mark a completed task as pending."""
        cursor = self.db_conn.cursor()
        cursor.execute(
            'UPDATE user_todo SET status = 0 WHERE id = ? AND user_id = ?',
            (task_id, ctx.author.id)
        )
        if cursor.rowcount == 0:
            return await ctx.send("❌ Task not found.")
        self.db_conn.commit()
        await ctx.send(f"✅ Task #{task_id} marked as pending!")

    @todo.command(name='list', aliases=['show'])
    async def todo_list(self, ctx):
        """Show your interactive TODO list. React to check/uncheck tasks."""
        cursor = self.db_conn.cursor()
        cursor.execute(
            'SELECT id, task, deadline, status FROM user_todo WHERE user_id = ? ORDER BY status ASC, id ASC',
            (ctx.author.id,)
        )
        tasks = cursor.fetchall()

        if not tasks:
            return await ctx.send("📝 Your TODO list is empty! Add tasks using `;todo add <task>`.")

        total_tasks = len(tasks)
        tasks = tasks[:10]
        
        embed = discord.Embed(title=f"📝 {ctx.author.display_name}'s TODO List", color=discord.Color.blue())
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        
        def build_embed(current_tasks):
            desc = ""
            mapping = {}
            for idx, (t_id, t_task, t_deadline, t_status) in enumerate(current_tasks):
                emoji = emojis[idx]
                mapping[emoji] = (t_id, t_status)
                
                checkbox = "✅" if t_status == 1 else "⬜"
                strike = "~~" if t_status == 1 else ""
                
                line = f"{emoji} {checkbox} **ID {t_id}:** {strike}{t_task}{strike}"
                if t_deadline:
                    line += f" *(Deadline: {t_deadline})*"
                desc += line + "\n\n"
            
            if total_tasks > 10:
                desc += f"\n*Showing 10 out of {total_tasks} tasks. Complete/remove some to see the rest.*"
                
            embed.description = desc
            return mapping

        task_mapping = build_embed(tasks)
        embed.set_footer(text="React with the corresponding number to toggle status, or ❌ to close.")

        msg = await ctx.send(embed=embed)
        
        for emoji in task_mapping.keys():
            await msg.add_reaction(emoji)
        await msg.add_reaction("❌")

        def check(reaction, user):
            return user == ctx.author and reaction.message.id == msg.id and str(reaction.emoji) in list(task_mapping.keys()) + ["❌"]

        while True:
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                
                if str(reaction.emoji) == "❌":
                    await msg.delete()
                    break
                    
                task_id, current_status = task_mapping[str(reaction.emoji)]
                new_status = 0 if current_status == 1 else 1
                
                cursor.execute(
                    'UPDATE user_todo SET status = ? WHERE id = ?',
                    (new_status, task_id)
                )
                self.db_conn.commit()
                    
                try:
                    await msg.remove_reaction(reaction.emoji, user)
                except discord.Forbidden:
                    pass
                    
                cursor.execute(
                    'SELECT id, task, deadline, status FROM user_todo WHERE user_id = ? ORDER BY status ASC, id ASC',
                    (ctx.author.id,)
                )
                updated_tasks = cursor.fetchall()
                    
                total_tasks = len(updated_tasks)
                updated_tasks = updated_tasks[:10]
                task_mapping = build_embed(updated_tasks)
                await msg.edit(embed=embed)

            except asyncio.TimeoutError:
                try:
                    await msg.clear_reactions()
                except discord.Forbidden:
                    pass
                break

def setup(bot):
    async def setup(bot):
        await bot.add_cog(Todo(bot))
