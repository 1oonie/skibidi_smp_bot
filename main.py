import config
import sys
import os
from typing import Sequence, Tuple

import discord
from discord import app_commands 
from discord import ui

if len(sys.argv) > 1:
    SYNC = sys.argv[1] == "sync"
else:
    SYNC = False

GUILD_ID = 1173746149438529616
GUILD = discord.Object(GUILD_ID)

PINBOARD = config.webhook_url
PINBOARD_CHANNEL = 1176620966600786052
PURGE_LOGS = 1176624025330524271


class Client(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        if SYNC:
            self.tree.copy_global_to(guild=GUILD)
            await self.tree.sync(guild=GUILD)
            print("Syncing guild commands to", GUILD_ID)
    
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is discord.InteractionType.component and interaction.data["custom_id"].startswith("update_roles"): # type: ignore
            role = int(interaction.data["custom_id"].split(":")[1]) # type: ignore
            obj = discord.Object(id=role)
            assert isinstance(interaction.user, discord.Member)

            if sum(role == r.id for r in interaction.user.roles):
                await interaction.user.remove_roles(obj)
                await interaction.response.send_message(f"Removed role <@&{role}>", ephemeral=True)
            else:
                await interaction.user.add_roles(obj)
                await interaction.response.send_message(f"Added role <@&{role}>", ephemeral=True)


class ConfirmationView(ui.View):
    def __init__(self, author: int):
        super().__init__(timeout=180)

        self.confirmed = None
        self.author = author

    @ui.button(label="Yes", style=discord.ButtonStyle.success)
    async def _button_yes(self, interaction: discord.Interaction, _):
        self.confirmed = True
        await interaction.response.defer()
        self.stop()

    @ui.button(label="No", style=discord.ButtonStyle.danger)
    async def _button_no(self, interaction: discord.Interaction, _):
        self.confirmed = False
        await interaction.response.defer()
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user.id == self.author


class RolePickerView(ui.View):
    def __init__(self, roles: Sequence[Tuple[int, str, str]]):
        super().__init__()
        for role in roles:
            self.create_role_button(*role)

    def create_role_button(self, role: int, emoji: str, label: str):
        self.add_item(
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label=label,
                emoji=emoji,
                custom_id=f"update_roles:{role}:{os.urandom(4).hex()}",
            )
        )


async def pin_message_helper(
    message: discord.Message,
    pinner: discord.Member | discord.User,
    guild: discord.Guild,
) -> discord.WebhookMessage:
    webhook = discord.Webhook.from_url(PINBOARD, client=client)
    r = await webhook.send(
        content=message.content,
        username=message.author.name,
        avatar_url=message.author.display_avatar.url,
        files=[await attachment.to_file() for attachment in message.attachments],
        wait=True,
    )
    channel = guild.get_channel(PINBOARD_CHANNEL)  # type: ignore
    assert isinstance(channel, discord.TextChannel)

    await channel.send(
        content=f"Message from {message.author.name} (`{message.author.id}`) pinned by {pinner.name} (`{pinner.id}`)",
        reference=channel.get_partial_message(r.id),
    )
    return r


client = Client(intents=discord.Intents.all())


@client.event
async def on_ready():
    assert client.user is not None
    print(f"Logged in as {client.user} (ID: {client.user.id})")
    print("------")


@client.event
async def on_audit_log_entry_create(event: discord.AuditLogEntry):
    if event.guild is None:
        return
    if event.action is discord.AuditLogAction.message_pin:
        if isinstance(event.extra.channel, discord.TextChannel):  # type: ignore
            channel = event.extra.channel  # type: ignore
        else:
            channel = event.guild.get_channel(event.extra.channel.id)  # type: ignore

        message = await channel.fetch_message(event.extra.message_id)  # type: ignore
        user = await client.fetch_user(event.user_id)  # type: ignore

        await pin_message_helper(message, user, event.guild)


@app_commands.command(name="purge", description="Purges the current channel")
async def purge(interaction: discord.Interaction):
    assert interaction.guild is not None

    if not isinstance(
        interaction.channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)
    ):
        return await interaction.response.send_message(
            "This command must be run in a text channel."
        )

    view = ConfirmationView(interaction.user.id)
    await interaction.response.send_message(
        "## Continue?\n\nThis command will permenantly purge all the messages of this channel. This action cannot be undone. Press `yes` to continue.",
        view=view,
    )
    await view.wait()
    if view.confirmed == False:
        return await interaction.channel.send("Action aborted.")

    message = await interaction.channel.send(
        "Fetching messages... This could take some time, please be patient."
    )
    messages = [m async for m in interaction.channel.history(limit=None)]
    await message.edit(content=f"Found `{len(messages)}` messages, purging.")
    await interaction.channel.purge(
        limit=len(messages),
        bulk=True,
        reason=f"Channel purge requested by {interaction.user.name} ({interaction.user.id})",
    )

    purge_logs = interaction.guild.get_channel(PURGE_LOGS)
    if purge_logs is not None and isinstance(purge_logs, discord.TextChannel):
        await purge_logs.send(
            f"`{len(messages)}` messages purged from {interaction.channel.mention} by {interaction.user.name} (`{interaction.user.id}`)"
        )


@app_commands.command(name="rolepicker", description="Sends the role picker")
async def rolepicker(interaction: discord.Interaction):
    roles = [
        (1173746689195118753, "\U0001f3ed", "iron"),
        (1173746759734923408, "\U0001f48d", "diamond"),
        (1173746849153298533, "\U0001f911", "netherite"),
        (1173747418488123452, "\U0001f434", "leather"),
        (1173747525333819553, "\U0001fa99", "gold"),
        (1173752077969788948, "\U000023f0", "2am")
    ]
    assert isinstance(interaction.channel, discord.TextChannel)
    view = RolePickerView(roles)
    await interaction.channel.send("Click the buttons below to receive various roles and if you want to remove a role you already have, click the button again", view=view)
    await interaction.response.send_message("Message sent successfully!", ephemeral=True)
    view.stop()


@app_commands.context_menu(name="Pin message")
async def pin_message(interaction: discord.Interaction, message: discord.Message):
    assert interaction.guild is not None
    await interaction.response.defer(ephemeral=True)
    r = await pin_message_helper(message, interaction.user, interaction.guild)
    await interaction.edit_original_response(
        content=f"Pinned message succesfully! {r.jump_url}"
    )


client.tree.add_command(purge)
client.tree.add_command(pin_message)
client.tree.add_command(rolepicker)

client.run(config.token)
