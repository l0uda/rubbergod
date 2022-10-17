import disnake
from disnake.ext import commands
from typing import Tuple, Union, List

import utils
from config.app_config import config

# TODO: use messages
from config.messages import Messages
from repository import role_group_repo
from features.reaction_context import ReactionContext

group_repo = role_group_repo.RoleGroupRepository()


class Roles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Returns list of role names and emotes that represent them
    async def get_join_role_data(self, message):
        input_string = message.content
        input_string = input_string.replace("**", "")
        try:
            input_string = input_string.rstrip().split("\n")
        except ValueError:
            await message.channel.send(utils.fill_message("role_format", user=message.author.id))
            return None
        output = []
        for line in input_string:
            try:
                out = line.split(" - ", 1)[0].split()
                out = [out[1], out[0]]
                output.append(out)
            except Exception:
                if message.channel.id not in config.role_channels:
                    msg = utils.fill_message(
                        "role_invalid_line", user=message.author.id, line=disnake.utils.escape_mentions(line)
                    )
                    await message.channel.send(msg)
        for line in output:
            if "<#" in line[0] or "<@" in line[0]:
                line[0] = line[0].replace("<#", "")
                line[0] = line[0].replace("<@&", "")
                line[0] = line[0].replace("<@", "")
                line[0] = line[0].replace(">", "")
                try:
                    line[0] = int(line[0])
                except Exception:
                    if message.channel.id not in config.role_channels:
                        msg = utils.fill_message(
                            "role_invalid_line",
                            user=message.author.id,
                            line=disnake.utils.escape_mentions(line[0]),
                        )
                        await message.channel.send(msg)
        return output

    # Adds reactions to message
    async def message_role_reactions(self, message, data):
        if message.channel.type is not disnake.ChannelType.text:
            await message.channel.send(Messages.role_not_on_server)
            guild = self.bot.get_guild(config.guild_id)
        else:
            guild = message.guild
        for line in data:
            roles, channels = self.get_target(line[0], guild)
            if roles == [None] and channels == [None]:
                msg = utils.fill_message(
                    "role_not_role", user=message.author.id, not_role=disnake.utils.escape_mentions(line[0])
                )
                await message.channel.send(msg)
            else:
                try:
                    await message.add_reaction(line[1])
                except disnake.errors.HTTPException:
                    msg = utils.fill_message(
                        "role_invalid_emote",
                        user=message.author.id,
                        not_emote=disnake.utils.escape_mentions(line[1]),
                        role=disnake.utils.escape_mentions(line[0]),
                    )
                    await message.channel.send(msg)

    async def add_perms(self, target, member, guild):
        """Add a target role / channel to a member."""
        roles, channels = self.get_target(target, guild)
        for role in roles:
            if role is not None and role not in member.roles:
                await member.add_roles(role)
        for channel in channels:
            if channel is not None:
                perms: disnake.PermissionOverwrite = channel.overwrites_for(member)

                if not perms.is_empty():
                    deny_exp_perm = disnake.Permissions()
                    deny_exp_perm.view_channel = True

                    perm_pair = perms.pair()
                    if deny_exp_perm.value == perm_pair[1].value and perm_pair[0].value == 0:
                        # User have only expected permission (Allow: None, Deny: view_channel).
                        # This configuration will remove overwrite before checks and set.
                        # This will prevent from removing higher permissions from channels (or bans).
                        await channel.set_permissions(member, overwrite=None)

                perms_for: disnake.Permissions = channel.permissions_for(member)
                if perms_for.administrator or perms_for.view_channel:  # Is mod, or now have access. Ignore
                    continue

                total_overwrites = len(channel.overwrites)
                if total_overwrites >= 490:
                    role = await self.create_role(channel)
                    await member.add_roles(role)
                else:
                    current_perms = channel.permissions_for(member)
                    if not current_perms.read_messages:
                        if not perms.is_empty():
                            perms.read_messages = True
                            await channel.set_permissions(member, overwrite=perms)
                        else:
                            await channel.set_permissions(member, read_messages=True)

    async def create_role(self, channel: disnake.abc.GuildChannel, ignore: disnake.Member = None):
        """Create a new role with the same name as channel name and transfer permissions"""
        keep = {}  # users and roles with special permission other then default read
        # prepare default permission for comparison
        default_perm = disnake.Permissions()
        default_perm.view_channel = True
        total_overwrites = len(channel.overwrites)
        rate = total_overwrites/100 * 5  # rate of progress bar update
        guild = self.bot.get_guild(config.guild_id)
        bot_dev = guild.get_channel(config.bot_dev_channel)
        role = await guild.create_role(name=channel.name)
        message = await bot_dev.send(utils.fill_message("role_create_start", role=role.name))
        for idx, item in enumerate(channel.overwrites):
            if type(item) == disnake.Member:
                if ignore and ignore.id == item.id:
                    pass
                elif channel.overwrites[item] != default_perm:
                    keep[item] = channel.overwrites[item]
                else:
                    await item.add_roles(role)
            else:
                keep[item] = channel.overwrites[item]

            if (idx % rate == 0):
                await message.edit(
                    utils.fill_message(
                        "role_create_progress",
                        perms=total_overwrites,
                        progress=utils.create_bar(idx + 1, total_overwrites),
                    )
                )

        await message.edit(
            utils.fill_message(
                "role_create_done",
                role=role.name,
                perms=len(role.members)
            )
        )

        # remove permission
        await channel.edit(sync_permissions=True)
        # add role
        await channel.set_permissions(role, read_messages=True)
        # restore special permissions
        for item in keep:
            await channel.set_permissions(item, overwrite=keep[item])
        return role

    async def remove_perms(self, target, member: disnake.Member, guild):
        """Remove a target role / channel from a member."""
        roles, channels = self.get_target(target, guild)
        for role in roles:
            if role is not None and role in member.roles:
                await member.remove_roles(role)
        for channel in channels:
            if channel is None:
                continue

            perms = channel.permissions_for(member)
            if perms.administrator:
                continue  # User have administrator permission and it's useless do some operation.

            overwrite = channel.overwrites_for(member)
            # if overwrite.is_empty():
            #    continue  # Overwrite not found. User maybe have access from role.

            total_overwrites = len(channel.overwrites)
            if total_overwrites >= 490:
                role = await self.create_role(channel, ignore=member)
            else:
                if overwrite != disnake.PermissionOverwrite(read_messages=True):
                    # Member have extra permissions and we don't want remove it.
                    # Instead of remove permission we set only read messages permission to deny.
                    overwrite.update(read_messages=False)
                    await channel.set_permissions(member, overwrite=overwrite)
                    continue

                await channel.set_permissions(member, overwrite=None)
                perms = channel.permissions_for(member)
                if perms.read_messages:
                    # The user still sees the channel. You need to create special permissions.
                    await channel.set_permissions(member, read_messages=False)

    def get_target(self, target, guild) -> Tuple[List[disnake.Role], List[disnake.abc.GuildChannel]]:
        """Detect if target is a channel a role or a group."""
        # Try a group first
        group = group_repo.get_group(target)
        if group is not None:
            roles, channels = [], []
            for role_id in group.role_ids:
                roles.append(disnake.utils.get(guild.roles, id=int(role_id)))
            for channel_id in group.channel_ids:
                channel = disnake.utils.get(guild.channels, id=int(channel_id))
                role = disnake.utils.get(guild.roles, name=channel.name)
                if role:
                    roles.append(role)
                else:
                    channels.append(channel)
            return roles, channels

        # if ID
        if isinstance(target, int) or target.isdigit():
            role = disnake.utils.get(guild.roles, id=int(target))
            channel = disnake.utils.get(guild.channels, id=int(target))
            if not role:
                role = disnake.utils.get(guild.roles, name=channel.name)
        # else if name of role / #channel
        else:
            target = target[1:] if target[0] == "#" else target
            role = disnake.utils.get(guild.roles, name=target)
            channel = disnake.utils.get(guild.channels, name=target.lower())

        return [role], [channel]

    @commands.check(utils.is_bot_admin)
    @commands.command()
    async def add_group(self, ctx, name: str):
        group_repo.add_group(name)
        await ctx.send(f"Pridal jsem groupu {name}")

    @commands.check(utils.is_bot_admin)
    @commands.command()
    async def get_group(self, ctx, name: str):
        group = group_repo.get_group(name)
        channels = ", ".join([f"<#{channel_id}>" for channel_id in group.channel_ids])
        await ctx.send(f"Jmeno: {group.name}\n" f"Channel IDs: {channels}\n" f"Role IDs:{group.role_ids}")

    @commands.check(utils.is_bot_admin)
    @commands.command()
    async def groups(self, ctx):
        names = group_repo.group_names()
        for name in names:
            await ctx.send(name)

    @commands.check(utils.is_bot_admin)
    @commands.command()
    async def add_channel_id(self, ctx, name: str, channel_id: int):
        group_repo.group_add_channel_id(name, channel_id)
        await ctx.send("Done")

    @commands.check(utils.is_bot_admin)
    @commands.command()
    async def add_role_id(self, ctx, name: str, role_id: int):
        group_repo.group_add_role_id(name, role_id)
        await ctx.send("Done")

    @commands.check(utils.is_bot_admin)
    @commands.command()
    async def group_reset_channels(self, ctx, name: str):
        group_repo.group_reset_channels(name)
        await ctx.send("Done")

    @commands.check(utils.is_bot_admin)
    @commands.command()
    async def group_reset_roles(self, ctx, name: str):
        group_repo.group_reset_roles(name)
        await ctx.send("Done")

    @commands.check(utils.is_bot_admin)
    @commands.slash_command(name="channel", guild_ids=[config.guild_id])
    async def channel(self, ctx):
        pass

    @channel.sub_command(name="copy", description=Messages.role_channel_copy_brief)
    async def copy(self, inter, src: Union[disnake.TextChannel, disnake.VoiceChannel],
                   dst: Union[disnake.TextChannel, disnake.VoiceChannel]):
        """
        Copy permissions from src channel to dst.
        Both channels are expected as tags or IDs
        """
        await inter.send(Messages.channel_copy_start)
        for key in src.overwrites:
            await dst.set_permissions(key, overwrite=src.overwrites[key])
        await inter.edit_original_message(Messages.channel_copy_done)

    @channel.sub_command(name="clone", description=Messages.role_channel_clone_brief)
    async def clone(self, inter, src: Union[disnake.TextChannel, disnake.VoiceChannel], name):
        """Clone channel with same permissions as src."""
        await inter.send(Messages.channel_clone_start)
        new = await src.clone(name=name)
        await inter.edit_original_message(utils.fill_message("channel_clone_done", id=new.id))

    @channel.sub_command(name="create", description=Messages.role_channel_create_brief)
    async def create(
        self,
        inter: disnake.ApplicationCommandInteraction,
        channel_name,
        role: disnake.Role,
        rate: int = commands.Param(ge=1, description=Messages.channel_create_rate),
        category: disnake.CategoryChannel = None
    ):

        await inter.send(Messages.channel_create_start)
        guild = inter.guild
        overwrites = {guild.default_role: disnake.PermissionOverwrite(view_channel=False)}
        channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)

        for index, member in enumerate(role.members):
            await channel.set_permissions(member, view_channel=True)
            if (index % rate == 0):
                await inter.edit_original_message(
                    f"• uživatelů: {len(role.members)}\n" + utils.create_bar(index+1, len(role.members))
                )

        await inter.edit_original_message(
            utils.fill_message(
                "channel_create_done",
                channel=channel.mention,
                role=role.name,
                perms=len(role.members)
            )
        )

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if message.channel.id in config.role_channels:
            role_data = await self.get_join_role_data(message)
            await self.message_role_reactions(message, role_data)

    async def handle_reaction(self, ctx: ReactionContext):
        role_data = await self.get_join_role_data(ctx.message)
        for line in role_data:
            if str(ctx.emoji) == line[1]:
                await self.add_perms(line[0], ctx.member, ctx.guild)
                break
        else:
            await ctx.message.remove_reaction(ctx.emoji, ctx.member)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        ctx: ReactionContext = await ReactionContext.from_payload(self.bot, payload)
        if ctx is None:
            return

        if ctx.channel.id in config.role_channels:
            role_data = await self.get_join_role_data(ctx.message)
            for line in role_data:
                if str(ctx.emoji) == line[1]:
                    await self.remove_perms(line[0], ctx.member, ctx.guild)
                    break

    @copy.error
    @clone.error
    async def error(self, ctx, error):
        """Print help on missing argument"""
        if isinstance(error, commands.MissingRequiredArgument):
            if "copy" in ctx.invoked_subcommand.name:
                await ctx.send(Messages.channel_copy_help)
            elif "clone" in ctx.invoked_subcommand.name:
                await ctx.send(Messages.channel_clone_help)
        else:
            # channel not found
            await ctx.send(error)


def setup(bot):
    bot.add_cog(Roles(bot))
