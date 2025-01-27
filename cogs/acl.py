import disnake
from disnake.ext import commands

import utils
from cogs import room_check
from features import acl
from config.app_config import config
from config import cooldowns
from repository import acl_repo

acl_repo = acl_repo.AclRepository()
acl = acl.Acl(acl_repo)


class Acl(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.check = room_check.RoomCheck(bot)
        self.mod = None

    @cooldowns.short_cooldown
    @commands.command()
    async def acl(self, ctx, *args):
        if self.mod is None:
            guild = self.bot.get_guild(config.guild_id)
            self.mod = disnake.utils.get(guild.roles, name="Mod")
        if self.mod in ctx.author.roles:
            if not len(args):
                await ctx.send(utils.fill_message("acl_help", user=ctx.author.id))
                return
            if args[0] == 'add':
                await acl.handle_add(ctx, args[1:])
            elif args[0] == 'del':
                await acl.handle_del(ctx, args[1:])
            elif args[0] == 'edit':
                await acl.handle_edit(ctx, args[1:])
            elif args[0] == 'list':
                await acl.handle_list(ctx, args[1:])
            else:
                await ctx.send(utils.fill_message("acl_help", user=ctx.author.id))
                return
        else:
            await ctx.send(utils.fill_message("missing_perms", user=ctx.author.id))
            return

    # TODO: this is only to help init the acl database
    # should be rewritten or removed later
    @cooldowns.short_cooldown
    @commands.command()
    async def acl_roles(self, ctx, *args):
        guild = self.bot.get_guild(config.guild_id)
        if self.mod is None:
            self.mod = disnake.utils.get(guild.roles, name="Mod")
        if self.mod in ctx.author.roles:
            rules = acl_repo.list_rule()
            rubbergod = disnake.utils.get(guild.roles, name="Rubbergod")
            rules = [rule.acl_snowflake for rule in rules]
            output = "Role pod Rubbergodem, které nejsou v ACL:\n```\n"
            for role in guild.roles:
                if str(role.id) not in rules and role < rubbergod:
                    output += str(role.name) + "  -  " + str(role.id) + "\n"

            await ctx.send(output + "\n```")


def setup(bot):
    bot.add_cog(Acl(bot))
