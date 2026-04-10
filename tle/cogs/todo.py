import math
import discord
from discord.ext import commands
from tle.util import codeforces_common as cf_common

class TodoPaginator(discord.ui.View):
    """A custom pagination view for Discord UI to handle multiple pages of tasks."""
    def __init__(self, ctx, title, entries, per_page=10):
        super().__init__(timeout=300) # 5-minute timeout for the buttons
        self.ctx = ctx
        self.title = title
        self.entries = entries
        self.per_page = per_page
        self.current_page = 0
        self.max_pages = max(1, math.ceil(len(entries) / per_page))
        self.update_buttons()

    def format_page(self):
        embed = discord.Embed(
            title=self.title, 
            color=discord.Color.green() if "History" in self.title else discord.Color.blue()
        )
        
        if not self.entries:
            embed.description = "Nothing to display here!"
            return embed

        start_idx = self.current_page * self.per_page
        end_idx = start_idx + self.per_page
        page_data = self.entries[start_idx:end_idx]
        
        desc = ""
        for idx, item in enumerate(page_data, start=start_idx + 1):
            if isinstance(item, tuple) or isinstance(item, list):
                # Expecting tuple like (task_id, task_desc)
                task_str = item[1] if len(item) > 1 else item[0]
                desc += f"**{idx}.** {task_str}\n" 
            else:
                desc += f"**{idx}.** {item}\n"
                
        embed.description = desc
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.max_pages} • Total Items: {len(self.entries)}")
        return embed

    def update_buttons(self):
        self.btn_prev.disabled = (self.current_page == 0)
        self.btn_next.disabled = (self.current_page == self.max_pages - 1)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="todo_prev", emoji="⬅️")
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("You cannot control this menu.", ephemeral=True)
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.format_page(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, custom_id="todo_next", emoji="➡️")
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("You cannot control this menu.", ephemeral=True)
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.format_page(), view=self)


class Todo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(brief='Todo list management', invoke_without_command=True)
    async def todo(self, ctx):
        """Manage your competitive programming todo list."""
        await ctx.send_help(ctx.command)

    @todo.command(name='list', brief='View your active todo list (with pages)')
    async def todo_list(self, ctx):
        """Displays your active tasks with pages."""
        data = cf_common.user_db.get_active_todos(ctx.author.id)

        if not data:
            return await ctx.send(embed=discord.Embed(title="Todo List", description="Your active todo list is completely empty! 🎉", color=discord.Color.green()))

        view = TodoPaginator(ctx, title=f"Todo List for {ctx.author.display_name}", entries=data)
        await ctx.send(embed=view.format_page(), view=view)

    @todo.command(name='history', brief='View your completed tasks')
    async def todo_history(self, ctx):
        """Displays tasks you have finished."""
        data = cf_common.user_db.get_completed_todos(ctx.author.id)

        if not data:
            return await ctx.send(embed=discord.Embed(title="Todo History", description="You haven't completed any tasks yet.", color=discord.Color.red()))

        view = TodoPaginator(ctx, title=f"Completed History for {ctx.author.display_name}", entries=data)
        await ctx.send(embed=view.format_page(), view=view)

    @todo.command(name='add', brief='Add a task to your list')
    async def todo_add(self, ctx, *, task: str):
        """Adds a new problem/task to your todo list."""
        cf_common.user_db.add_todo(ctx.author.id, task)
        await ctx.send(f"✅ Added to your active todo list:\n`{task}`")

    @todo.command(name='done', brief='Mark a task as completed')
    async def todo_done(self, ctx, task_number: int):
        """Marks a task as done, moving it to your history."""
        active_tasks = cf_common.user_db.get_active_todos(ctx.author.id)
        
        if task_number < 1 or task_number > len(active_tasks):
            return await ctx.send(f"❌ Invalid task number. You currently have {len(active_tasks)} active tasks.")
            
        task_item = active_tasks[task_number - 1]
        
        # Checking if DB returns (task_id, task_description)
        if isinstance(task_item, tuple) and len(task_item) > 1:
            task_id = task_item[0]
            cf_common.user_db.mark_todo_done(task_id)
        else:
            # Fallback if DB returns just description strings
            task_desc = task_item[0] if isinstance(task_item, tuple) else task_item
            cf_common.user_db.mark_todo_done_by_desc(ctx.author.id, task_desc)

        await ctx.send(f"✅ Marked task **#{task_number}** as completed! Moved to your history.")


async def setup(bot):
    await bot.add_cog(Todo(bot))
