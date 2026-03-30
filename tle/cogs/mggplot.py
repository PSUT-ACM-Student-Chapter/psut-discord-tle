import datetime
import logging
import inspect
from discord.ext import commands
from tle.util import codeforces_common as cf_common

class MonthlyGitGudPlot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(self.__class__.__name__)

    @commands.command(brief='Plot CF rating for top monthly git gudders', usage='[+zoom] [+points] [num_users]')
    async def ggplot(self, ctx, *args: str):
        """Plots the Codeforces rating history of the top monthly git gudders.
        
        By default, plots the top 5 users for the current month.
        You can specify the number of users to plot (up to 10).
        """
        args = list(args)
        zoom = False
        points = False
        
        # Parse standard plot flags
        if '+zoom' in args:
            zoom = True
            args.remove('+zoom')
        if '+points' in args:
            points = True
            args.remove('+points')

        # Determine the number of users to plot (default 5, max 10 to avoid API spam)
        num_users = 5
        if args and args[0].isdigit():
            num_users = int(args[0])
            num_users = max(1, min(num_users, 10)) 

        # Get timestamp for the start of the current month
        now = datetime.datetime.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()

        try:
            # Attempt to query the standard TLE gitgud table structure
            query = '''
                SELECT user_id
                FROM gitgud
                WHERE guild_id = ? AND time >= ?
                GROUP BY user_id
                ORDER BY COUNT(*) DESC
                LIMIT ?
            '''
            res = cf_common.user_db.conn.execute(query, (str(ctx.guild.id), start_of_month, num_users)).fetchall()
        except Exception as e:
            self.logger.warning(f"Error querying gitgud table with 'time', falling back: {e}")
            try:
                # Fallback for some forks that might use 'timestamp' instead of 'time'
                query = '''
                    SELECT user_id
                    FROM gitgud
                    WHERE guild_id = ? AND timestamp >= ?
                    GROUP BY user_id
                    ORDER BY COUNT(*) DESC
                    LIMIT ?
                '''
                res = cf_common.user_db.conn.execute(query, (str(ctx.guild.id), start_of_month, num_users)).fetchall()
            except Exception as ex:
                self.logger.error(f"Error querying gitgud table: {ex}")
                return await ctx.send(f"Failed to fetch git gudders from database. Check schema. Error: `{ex}`")

        if not res:
            return await ctx.send("No git guds found for this month.")

        user_ids = [row[0] for row in res]
        
        # Resolve user IDs to Codeforces handles
        handles = []
        for uid in user_ids:
            handle = cf_common.user_db.get_handle(uid, ctx.guild.id)
            if handle:
                handles.append(handle)
        
        if not handles:
            return await ctx.send("Could not find Codeforces handles for the top git gudders.")

        # Grab the existing `plot` command from the Graphs cog
        plot_cmd = self.bot.get_command('plot')
        if plot_cmd:
            plot_args = []
            if zoom: plot_args.append('+zoom')
            if points: plot_args.append('+points')
            plot_args.extend(handles)
            
            await ctx.send(f"Generating plot for top {len(handles)} monthly git gudders: `{'`, `'.join(handles)}`")
            
            # Invoke the original +plot command natively with the resolved handles
            await ctx.invoke(plot_cmd, *plot_args)
        else:
            await ctx.send("The `+plot` command could not be found. Make sure the Graphs cog is loaded.")

async def setup(bot):
    # This setup function uses the discord.py 2.x standard which TLE uses natively
    await bot.add_cog(MonthlyGitGudPlot(bot))
