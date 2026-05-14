import discord
from discord.ext import commands
import json
import os
import asyncio
from groq import Groq

# ─── CONFIG ──────────────────────────────────────────────────────────────────
OWNER_ID = 1191963306785787946
REQUIRED_GUILD_INVITE = "https://discord.gg/2PvXETvFFG"
PREFIX = "+"
DATA_FILE = "data.json"

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

# ─── INTENTS ─────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
intents.invites = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)
groq_client = Groq(api_key=GROQ_API_KEY)

# ─── INVITE CACHE ────────────────────────────────────────────────────────────
invite_cache: dict[int, dict[str, int]] = {}

# ─── DATA ────────────────────────────────────────────────────────────────────
def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        data = {"users": {}, "sessions": {}}
        save_data(data)
        return data
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_user(user_id: int) -> dict:
    data = load_data()
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {"points": 0, "invites": 0, "used_points": 0}
        save_data(data)
    return data["users"][uid]

def update_user(user_id: int, **kwargs):
    data = load_data()
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {"points": 0, "invites": 0, "used_points": 0}
    data["users"][uid].update(kwargs)
    save_data(data)

def get_session(user_id: int) -> dict | None:
    return load_data()["sessions"].get(str(user_id))

def set_session(user_id: int, session: dict):
    data = load_data()
    data["sessions"][str(user_id)] = session
    save_data(data)

def clear_session(user_id: int):
    data = load_data()
    data["sessions"].pop(str(user_id), None)
    save_data(data)

# ─── QUESTIONS ───────────────────────────────────────────────────────────────
QUESTIONS = [
    ("purpose",     "**[1/7]** Quel est le thème ou l'objectif de ton serveur ?"),
    ("memberCount", "**[2/7]** Quelle taille est prévue ? *(ex: Petit, Moyen, Grand)*"),
    ("roles",       "**[3/7]** Quels rôles souhaites-tu ? *(ex: Admin, VIP, Membre)*"),
    ("channels",    "**[4/7]** Quels salons spécifiques veux-tu inclure ?"),
    ("emojis",      "**[5/7]** Emojis dans les noms de salons ? *(oui / non)*"),
    ("language",    "**[6/7]** Langue du serveur ? *(ex: Français, Anglais)*"),
    ("style",       "**[7/7]** Style souhaité ? *(ex: Professionnel, Gaming, Fun)*"),
]

# ─── GROQ AI ─────────────────────────────────────────────────────────────────
async def build_discord_server(guild: discord.Guild, config: dict) -> dict:
    results = {"roles": [], "categories": [], "channels": [], "errors": []}

    for channel in list(guild.channels):
        try:
            if channel.permissions_for(guild.me).manage_channels:
                await channel.delete()
                await asyncio.sleep(0.4)
        except Exception as e:
            results["errors"].append(f"Del channel {channel.name}: {e}")

    for role in list(guild.roles):
        if role.name != "@everyone" and not role.managed and role != guild.me.top_role:
            try:
                await role.delete()
                await asyncio.sleep(0.4)
            except Exception as e:
                results["errors"].append(f"Del role {role.name}: {e}")

    for role_data in config.get("roles", []):
        try:
            color_hex = role_data.get("color", "#99AAB5").lstrip("#")
            color = discord.Color(int(color_hex, 16))
            role = await guild.create_role(
                name=role_data["name"],
                color=color,
                hoist=role_data.get("hoist", False),
                mentionable=role_data.get("mentionable", False),
            )
            results["roles"].append(role.name)
            await asyncio.sleep(0.4)
        except Exception as e:
            results["errors"].append(f"Role {role_data.get('name')}: {e}")

    for cat_data in config.get("categories", []):
        try:
            category = await guild.create_category(cat_data["name"])
            results["categories"].append(category.name)
            await asyncio.sleep(0.4)

            for chan_data in cat_data.get("channels", []):
                try:
                    if chan_data.get("type") == "voice":
                        ch = await guild.create_voice_channel(chan_data["name"], category=category)
                    else:
                        ch = await guild.create_text_channel(
                            chan_data["name"],
                            category=category,
                            topic=chan_data.get("topic", ""),
                        )
                    results["channels"].append(ch.name)
                    await asyncio.sleep(0.4)
                except Exception as e:
                    results["errors"].append(f"Channel {chan_data.get('name')}: {e}")
        except Exception as e:
            results["errors"].append(f"Category {cat_data.get('name')}: {e}")

    if config.get("serverName"):
        try:
            await guild.edit(name=config["serverName"])
        except Exception as e:
            results["errors"].append(f"Rename: {e}")

    return results


# ─── VERIFY REQUIRED GUILD ───────────────────────────────────────────────────
async def is_on_required_guild(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    for guild in bot.guilds:
        try:
            invites = await guild.invites()
            if any(inv.code == "45zytfB8gv" for inv in invites):
                try:
                    await guild.fetch_member(user_id)
                    return True
                except discord.NotFound:
                    pass
        except (discord.Forbidden, discord.HTTPException):
            pass
    return False


# ─── PERSISTENT VIEW ─────────────────────────────────────────────────────────
class PersistentEmbedView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Support", style=discord.ButtonStyle.secondary, emoji="🎫", custom_id="persistent_support")
    async def support_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        e = discord.Embed(
            description="Pour toute assistance, contacte un membre du staff ou ouvre un ticket sur le serveur officiel.",
            color=0x2B2D31
        )
        await interaction.response.send_message(embed=e, ephemeral=True)

    @discord.ui.button(label="Générer un serveur", style=discord.ButtonStyle.primary, emoji="⚡", custom_id="persistent_generate")
    async def generate_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user

        if not interaction.guild:
            e = discord.Embed(description="Utilise cette commande dans un serveur.", color=0xED4245)
            return await interaction.response.send_message(embed=e, ephemeral=True)

        if not interaction.user.guild_permissions.administrator and interaction.user.id != OWNER_ID:
            e = discord.Embed(description="Permissions insuffisantes.", color=0xED4245)
            return await interaction.response.send_message(embed=e, ephemeral=True)

        if not await is_on_required_guild(user.id):
            e = discord.Embed(description=f"Accès refusé. Rejoins le serveur officiel : {REQUIRED_GUILD_INVITE}", color=0xED4245)
            return await interaction.response.send_message(embed=e, ephemeral=True)

        udata = get_user(user.id)
        if udata["points"] <= 0 and user.id != OWNER_ID:
            e = discord.Embed(
                description=f"Crédits insuffisants. Invite des membres sur {REQUIRED_GUILD_INVITE} pour en obtenir.\n**Crédits : {udata['points']}**",
                color=0xED4245
            )
            return await interaction.response.send_message(embed=e, ephemeral=True)

        if get_session(user.id):
            e = discord.Embed(description="Une session est déjà en cours dans tes DMs.", color=0xFEE75C)
            return await interaction.response.send_message(embed=e, ephemeral=True)

        set_session(user.id, {"guild_id": interaction.guild.id, "step": 0, "answers": {}})

        try:
            welcome = discord.Embed(
                title="Generate",
                description=f"**{len(QUESTIONS)} questions** — Réponds dans ce DM.\n\n⚠️ Tous les salons et rôles existants seront supprimés.\n\n**Crédits :** {'∞' if user.id == OWNER_ID else udata['points']}",
                color=0x2B2D31
            )
            await user.send(embed=welcome)
            _, first_q = QUESTIONS[0]
            await user.send(embed=discord.Embed(description=first_q, color=0x2B2D31))
            await interaction.response.send_message(embed=discord.Embed(description="Questionnaire envoyé en DM.", color=0x57F287), ephemeral=True)
        except discord.Forbidden:
            clear_session(user.id)
            e = discord.Embed(description="Impossible d'envoyer un DM. Active les messages privés.", color=0xED4245)
            await interaction.response.send_message(embed=e, ephemeral=True)


# ─── EVENTS ──────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ {bot.user} connecté.")
    bot.add_view(PersistentEmbedView())
    for guild in bot.guilds:
        try:
            invs = await guild.invites()
            invite_cache[guild.id] = {inv.code: inv.uses for inv in invs}
        except Exception:
            pass


@bot.event
async def on_guild_join(guild: discord.Guild):
    try:
        invs = await guild.invites()
        invite_cache[guild.id] = {inv.code: inv.uses for inv in invs}
    except Exception:
        pass


@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    try:
        new_invites = await guild.invites()
        old_invites = invite_cache.get(guild.id, {})
        used = next(
            (inv for inv in new_invites
             if inv.uses > old_invites.get(inv.code, 0) and inv.inviter),
            None
        )
        invite_cache[guild.id] = {inv.code: inv.uses for inv in new_invites}
        if used and used.code == "45zytfB8gv" and used.inviter:
            inviter_id = used.inviter.id
            user = get_user(inviter_id)
            update_user(inviter_id, points=user["points"] + 1, invites=user["invites"] + 1)
    except Exception as e:
        print(f"Invite tracking error: {e}")


# ─── DM HANDLER ──────────────────────────────────────────────────────────────
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if isinstance(message.channel, discord.DMChannel) and not message.content.startswith(PREFIX):
        session = get_session(message.author.id)
        if not session:
            return

        step = session["step"]
        key, _ = QUESTIONS[step]
        session["answers"][key] = message.content
        session["step"] += 1
        set_session(message.author.id, session)

        if session["step"] < len(QUESTIONS):
            _, next_q = QUESTIONS[session["step"]]
            embed = discord.Embed(description=next_q, color=0x2B2D31)
            await message.channel.send(embed=embed)
        else:
            await _process_generation(message.channel, message.author, session)
        return

    await bot.process_commands(message)


async def _process_generation(channel: discord.DMChannel, author: discord.User, session: dict):
    clear_session(author.id)

    embed = discord.Embed(description="Génération en cours...", color=0x2B2D31)
    msg = await channel.send(embed=embed)

    try:
        config = await asyncio.get_event_loop().run_in_executor(
            None, lambda: groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "Tu réponds uniquement en JSON valide, sans texte autour."},
                    {"role": "user", "content": f"""Expert Discord. Génère un JSON pour ce serveur :
{json.dumps(session['answers'], ensure_ascii=False)}

Format :
{{"serverName":"...","serverDescription":"...","categories":[{{"name":"CAT","channels":[{{"name":"salon","type":"text","topic":"..."}}]}}],"roles":[{{"name":"Rôle","color":"#HEX","hoist":true,"mentionable":true}}],"welcomeMessage":"...","rules":["..."]}}

JSON VALIDE UNIQUEMENT."""}
                ],
                max_tokens=2048, temperature=0.7
            )
        )
        raw = config.choices[0].message.content
        start = raw.find("{"); end = raw.rfind("}") + 1
        config_data = json.loads(raw[start:end])

        preview = discord.Embed(
            title=config_data.get("serverName", "Serveur"),
            description=config_data.get("serverDescription", ""),
            color=0x5865F2
        )
        preview.add_field(name="Catégories", value=str(len(config_data.get("categories", []))), inline=True)
        preview.add_field(name="Salons", value=str(sum(len(c.get("channels", [])) for c in config_data.get("categories", []))), inline=True)
        preview.add_field(name="Rôles", value=str(len(config_data.get("roles", []))), inline=True)
        preview.set_footer(text="Application dans 3 secondes...")
        await msg.edit(embed=preview)
        await asyncio.sleep(3)

        build_embed = discord.Embed(description="Application en cours... ⚠️ Ne modifie rien.", color=0x2B2D31)
        await channel.send(embed=build_embed)

        guild = bot.get_guild(session["guild_id"])
        if not guild:
            raise ValueError("Serveur introuvable.")

        results = await build_discord_server(guild, config_data)

        if author.id != OWNER_ID:
            user = get_user(author.id)
            update_user(author.id,
                        points=max(0, user["points"] - 1),
                        used_points=user["used_points"] + 1)

        done = discord.Embed(
            title=config_data.get("serverName", "Serveur"),
            description=config_data.get("welcomeMessage", ""),
            color=0x57F287
        )
        done.add_field(name="Rôles", value=", ".join(results["roles"]) or "—", inline=False)
        done.add_field(name="Catégories", value=", ".join(results["categories"][:5]) or "—", inline=False)
        done.add_field(name="Salons créés", value=str(len(results["channels"])), inline=True)
        rules = config_data.get("rules", [])
        if rules:
            done.add_field(
                name="Règles",
                value="\n".join(f"{i+1}. {r}" for i, r in enumerate(rules[:5])),
                inline=False
            )
        if results["errors"]:
            done.add_field(name="Avertissements", value="\n".join(results["errors"][:3]), inline=False)
        user_data = get_user(author.id)
        done.set_footer(text="Owner" if author.id == OWNER_ID else f"Crédits restants : {user_data['points']}")
        await channel.send(embed=done)

    except Exception as e:
        clear_session(author.id)
        err = discord.Embed(description=f"Erreur : `{e}`\nTes crédits n'ont pas été déduits.", color=0xED4245)
        await channel.send(embed=err)


# ─── GENERATE ────────────────────────────────────────────────────────────────
@bot.command(name="generate")
async def cmd_generate(ctx: commands.Context):
    if not ctx.guild:
        return await ctx.send(embed=discord.Embed(description="Utilise cette commande dans un serveur.", color=0xED4245))

    if not ctx.author.guild_permissions.administrator and ctx.author.id != OWNER_ID:
        return await ctx.send(embed=discord.Embed(description="Permissions insuffisantes.", color=0xED4245))

    if not await is_on_required_guild(ctx.author.id):
        e = discord.Embed(description=f"Accès refusé. Rejoins le serveur officiel : {REQUIRED_GUILD_INVITE}", color=0xED4245)
        return await ctx.send(embed=e)

    user = get_user(ctx.author.id)
    if user["points"] <= 0 and ctx.author.id != OWNER_ID:
        e = discord.Embed(
            description=f"Crédits insuffisants. Invite des membres sur {REQUIRED_GUILD_INVITE} pour en obtenir.\n**Crédits : {user['points']}**",
            color=0xED4245
        )
        return await ctx.send(embed=e)

    if get_session(ctx.author.id):
        return await ctx.send(embed=discord.Embed(description="Une session est déjà en cours dans tes DMs.", color=0xFEE75C))

    set_session(ctx.author.id, {"guild_id": ctx.guild.id, "step": 0, "answers": {}})

    try:
        welcome = discord.Embed(
            title="Generate",
            description=f"**{len(QUESTIONS)} questions** — Réponds dans ce DM.\n\n⚠️ Tous les salons et rôles existants seront supprimés.\n\n**Crédits :** {'∞' if ctx.author.id == OWNER_ID else user['points']}",
            color=0x2B2D31
        )
        await ctx.author.send(embed=welcome)
        _, first_q = QUESTIONS[0]
        await ctx.author.send(embed=discord.Embed(description=first_q, color=0x2B2D31))
        await ctx.send(embed=discord.Embed(description="Questionnaire envoyé en DM.", color=0x57F287))
    except discord.Forbidden:
        clear_session(ctx.author.id)
        await ctx.send(embed=discord.Embed(description="Impossible d'envoyer un DM. Active les messages privés.", color=0xED4245))


# ─── EMBED (Owner) ────────────────────────────────────────────────────────────
@bot.command(name="embed")
async def cmd_embed(ctx: commands.Context):
    if ctx.author.id != OWNER_ID:
        return

    try:
        await ctx.message.delete()
    except Exception:
        pass

    main = discord.Embed(
        title="Generate",
        description=(
            "Génère un serveur Discord complet et personnalisé via l'IA.\n\n"
            "**Catégories · Salons · Rôles · Règles · Message de bienvenue**\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**Accès**\n"
            f"Rejoins le serveur officiel → {REQUIRED_GUILD_INVITE}\n"
            "Invite des membres pour obtenir des crédits.\n"
            "**1 invitation = 1 crédit = 1 génération**\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**Utilisation**\n"
            "`+generate` sur ton serveur → Réponds aux questions en DM → Le serveur est construit automatiquement."
        ),
        color=0x2B2D31
    )
    main.set_thumbnail(url=bot.user.display_avatar.url)

    await ctx.send(embed=main, view=PersistentEmbedView())


# ─── COMMANDES OWNER ─────────────────────────────────────────────────────────
def owner_only():
    async def predicate(ctx):
        return ctx.author.id == OWNER_ID
    return commands.check(predicate)


@bot.command(name="help")
@owner_only()
async def cmd_help(ctx: commands.Context):
    embed = discord.Embed(title="Commandes", color=0x2B2D31)
    embed.add_field(name="Utilisateurs", value="`+generate`", inline=False)
    embed.add_field(name="Owner", value=(
        "`+embed` · `+profile @user` · `+addpoints @user <n>`\n"
        "`+removepoints @user <n>` · `+setpoints @user <n>`\n"
        "`+userinfo @user` · `+resetuser @user` · `+listusers`"
    ), inline=False)
    await ctx.send(embed=embed)


@bot.command(name="profile")
@owner_only()
async def cmd_profile(ctx: commands.Context, member: discord.Member = None):
    target = member or ctx.author
    user = get_user(target.id)
    is_owner = target.id == OWNER_ID
    embed = discord.Embed(title=target.name, color=0xFFD700 if is_owner else 0x2B2D31)
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="Crédits", value=str(user["points"]), inline=True)
    embed.add_field(name="Invitations", value=str(user["invites"]), inline=True)
    embed.add_field(name="Générations", value=str(user["used_points"]), inline=True)
    embed.add_field(name="Statut", value="Owner" if is_owner else "Membre", inline=True)
    await ctx.send(embed=embed)


@bot.command(name="invites")
@owner_only()
async def cmd_invites(ctx: commands.Context, member: discord.Member = None):
    target = member or ctx.author
    user = get_user(target.id)
    embed = discord.Embed(
        description=f"**{target.name}** — {user['invites']} invitation(s) · {user['points']} crédit(s)",
        color=0x2B2D31
    )
    await ctx.send(embed=embed)


@bot.command(name="addpoints")
@owner_only()
async def cmd_addpoints(ctx, member: discord.Member, amount: int):
    user = get_user(member.id)
    update_user(member.id, points=user["points"] + amount)
    await ctx.send(embed=discord.Embed(
        description=f"**+{amount}** crédits → **{member.name}** — Total : **{user['points'] + amount}**",
        color=0x57F287
    ))


@bot.command(name="removepoints")
@owner_only()
async def cmd_removepoints(ctx, member: discord.Member, amount: int):
    user = get_user(member.id)
    new = max(0, user["points"] - amount)
    update_user(member.id, points=new)
    await ctx.send(embed=discord.Embed(
        description=f"**-{amount}** crédits → **{member.name}** — Total : **{new}**",
        color=0xFEE75C
    ))


@bot.command(name="setpoints")
@owner_only()
async def cmd_setpoints(ctx, member: discord.Member, amount: int):
    update_user(member.id, points=amount)
    await ctx.send(embed=discord.Embed(
        description=f"Crédits de **{member.name}** définis à **{amount}**",
        color=0x5865F2
    ))


@bot.command(name="addchannels")
@owner_only()
async def cmd_addchannels(ctx, member: discord.Member, amount: int):
    user = get_user(member.id)
    update_user(member.id, points=user["points"] + amount)
    await ctx.send(embed=discord.Embed(
        description=f"**+{amount}** crédits ajoutés → **{member.name}**",
        color=0x57F287
    ))


@bot.command(name="userinfo")
@owner_only()
async def cmd_userinfo(ctx, member: discord.Member):
    user = get_user(member.id)
    embed = discord.Embed(title=member.name, color=0x2B2D31)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=str(member.id), inline=True)
    embed.add_field(name="Crédits", value=str(user["points"]), inline=True)
    embed.add_field(name="Invitations", value=str(user["invites"]), inline=True)
    embed.add_field(name="Générations", value=str(user["used_points"]), inline=True)
    await ctx.send(embed=embed)


@bot.command(name="resetuser")
@owner_only()
async def cmd_resetuser(ctx, member: discord.Member):
    update_user(member.id, points=0, invites=0, used_points=0)
    await ctx.send(embed=discord.Embed(
        description=f"**{member.name}** réinitialisé.",
        color=0xED4245
    ))


@bot.command(name="listusers")
@owner_only()
async def cmd_listusers(ctx):
    data = load_data()
    users = list(data["users"].items())
    if not users:
        return await ctx.send(embed=discord.Embed(description="Aucun utilisateur.", color=0x2B2D31))

    lines = []
    for uid, udata in users[:20]:
        try:
            user = await bot.fetch_user(int(uid))
            name = user.name
        except Exception:
            name = uid
        lines.append(f"**{name}** — {udata['points']} crédits · {udata['invites']} invitations")

    embed = discord.Embed(
        title=f"Utilisateurs ({len(users)})",
        description="\n".join(lines),
        color=0x2B2D31
    )
    embed.set_footer(text="20 max affichés")
    await ctx.send(embed=embed)


@cmd_help.error
@cmd_profile.error
@cmd_invites.error
@cmd_addpoints.error
@cmd_removepoints.error
@cmd_setpoints.error
@cmd_addchannels.error
@cmd_userinfo.error
@cmd_resetuser.error
@cmd_listusers.error
async def owner_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        return


# ─── LANCEMENT ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
