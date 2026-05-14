import discord
from discord.ext import commands
import json
import os
import asyncio
from groq import Groq

# ─── CONFIG ──────────────────────────────────────────────────────────────────
OWNER_ID = 1191963306785787946 # Remplace par ton ID Discord
REQUIRED_GUILD_INVITE = "https://discord.gg/45zytfB8gv"
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
    ("purpose",     "🎯 **Quel est le but de ton serveur Discord ?**\n\nExemples : Gaming, Communauté, Étude, Business, Fanbase, Streaming...\nSois précis pour que l'IA crée quelque chose de parfait !"),
    ("memberCount", "👥 **Combien de membres tu prévois sur ton serveur ?**\n\nExemples : Petit (1-50), Moyen (50-500), Grand (500-5000), Très grand (5000+)"),
    ("roles",       "🎭 **Quels types de rôles tu veux sur ton serveur ?**\n\nExemples : Admin, Modérateur, VIP, Membre, Nouveau, Staff, Booster...\nTu peux en lister plusieurs !"),
    ("channels",    "💬 **Quels salons spéciaux tu veux avoir ?**\n\nExemples : Annonces, Règles, Général, Aide, Off-topic, Jeux, Musique, Salons vocaux..."),
    ("emojis",      "✨ **Tu veux des emojis dans les noms de salons et catégories ?**\n\nRéponds **oui** ou **non** (avec oui, les salons auront des emojis stylés 🔥)"),
    ("language",    "🌍 **Le serveur sera en quelle langue ?**\n\nExemples : Français, Anglais, Bilingue FR/EN..."),
    ("style",       "🎨 **Quel style tu veux pour ton serveur ?**\n\nExemples : Professionnel, Décontracté, Fun, Sérieux, Anime, Gaming..."),
]

# ─── GROQ AI ─────────────────────────────────────────────────────────────────
async def generate_server_config(answers: dict) -> dict:
    prompt = f"""Tu es un expert en création de serveurs Discord.
L'utilisateur veut créer un serveur avec ces informations :
{json.dumps(answers, ensure_ascii=False, indent=2)}

Génère une configuration complète en JSON UNIQUEMENT, sans texte avant ou après.

Format exact :
{{
  "serverName": "Nom du serveur",
  "serverDescription": "Description courte",
  "categories": [
    {{
      "name": "NOM CATÉGORIE",
      "channels": [
        {{"name": "nom-salon", "type": "text", "topic": "Sujet du salon"}},
        {{"name": "salon-vocal", "type": "voice"}}
      ]
    }}
  ],
  "roles": [
    {{"name": "Nom du rôle", "color": "#HEX", "hoist": true, "mentionable": true}}
  ],
  "welcomeMessage": "Message de bienvenue avec emojis",
  "rules": ["Règle 1", "Règle 2", "Règle 3"]
}}

Adapte parfaitement au thème. Utilise des emojis dans les noms si demandé.
RÉPONDS UNIQUEMENT EN JSON VALIDE."""

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "Tu réponds uniquement en JSON valide, sans texte autour."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=2048,
        temperature=0.7,
    )

    raw = response.choices[0].message.content
    start = raw.find("{")
    end = raw.rfind("}") + 1
    return json.loads(raw[start:end])


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


# ─── EVENTS ──────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
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
            print(f"📨 {used.inviter} a invité {member} → +1 point")
    except Exception as e:
        print(f"Erreur tracking invite: {e}")


# ─── DM HANDLER (questionnaire) ──────────────────────────────────────────────
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
            embed = discord.Embed(
                title=f"Question {session['step'] + 1}/{len(QUESTIONS)}",
                description=next_q,
                color=0x5865F2
            )
            embed.set_footer(text=f"Réponse précédente : « {message.content[:50]} »")
            await message.channel.send(embed=embed)
        else:
            await _process_generation(message.channel, message.author, session)
        return

    await bot.process_commands(message)


async def _process_generation(channel: discord.DMChannel, author: discord.User, session: dict):
    clear_session(author.id)

    processing_embed = discord.Embed(
        title="⚙️ Génération en cours...",
        description="L'IA **Groq (Llama 3.3 70B)** analyse tes réponses et génère la configuration parfaite...\n\n*Quelques secondes ⏳*",
        color=0xFEE75C
    )
    answers_text = "\n".join(f"• **{k}** : {v[:50]}" for k, v in session["answers"].items())
    processing_embed.add_field(name="📊 Tes réponses", value=answers_text, inline=False)
    msg = await channel.send(embed=processing_embed)

    try:
        config = await asyncio.get_event_loop().run_in_executor(
            None, lambda: groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "Tu réponds uniquement en JSON valide, sans texte autour."},
                    {"role": "user", "content": f"""Tu es un expert Discord. Génère un JSON de configuration pour ce serveur :
{json.dumps(session['answers'], ensure_ascii=False)}

Format :
{{"serverName":"...","serverDescription":"...","categories":[{{"name":"CAT","channels":[{{"name":"salon","type":"text","topic":"..."}}]}}],"roles":[{{"name":"Rôle","color":"#HEX","hoist":true,"mentionable":true}}],"welcomeMessage":"...","rules":["..."]}}

RÉPONDS UNIQUEMENT EN JSON VALIDE."""}
                ],
                max_tokens=2048, temperature=0.7
            )
        )
        raw = config.choices[0].message.content
        start = raw.find("{"); end = raw.rfind("}") + 1
        config_data = json.loads(raw[start:end])

        preview_embed = discord.Embed(
            title="✅ Configuration générée !",
            description=f"**{config_data.get('serverName', '?')}** — {config_data.get('serverDescription', '')}",
            color=0x57F287
        )
        preview_embed.add_field(name="📁 Catégories", value=str(len(config_data.get("categories", []))), inline=True)
        preview_embed.add_field(name="💬 Salons", value=str(sum(len(c.get("channels", [])) for c in config_data.get("categories", []))), inline=True)
        preview_embed.add_field(name="🎭 Rôles", value=str(len(config_data.get("roles", []))), inline=True)
        preview_embed.set_footer(text="Construction dans 3 secondes...")
        await msg.edit(embed=preview_embed)
        await asyncio.sleep(3)

        build_embed = discord.Embed(
            title="🔨 Construction en cours...",
            description="Application sur ton serveur Discord...\n⚠️ Ne modifie rien pendant ce processus !",
            color=0xFEE75C
        )
        await channel.send(embed=build_embed)

        guild = bot.get_guild(session["guild_id"])
        if not guild:
            raise ValueError("Serveur introuvable. Réinvite le bot !")

        results = await build_discord_server(guild, config_data)

        if author.id != OWNER_ID:
            user = get_user(author.id)
            update_user(author.id,
                        points=max(0, user["points"] - 1),
                        used_points=user["used_points"] + 1)

        success_embed = discord.Embed(
            title="🎉 Serveur créé avec succès !",
            description=f"{config_data.get('welcomeMessage', '**Bienvenue !**')}",
            color=0x57F287
        )
        success_embed.add_field(name="✅ Rôles", value=", ".join(results["roles"]) or "Aucun", inline=False)
        success_embed.add_field(name="📁 Catégories", value=", ".join(results["categories"][:5]) or "Aucune", inline=False)
        success_embed.add_field(name="💬 Salons créés", value=str(len(results["channels"])), inline=True)
        rules = config_data.get("rules", [])
        if rules:
            success_embed.add_field(
                name="📜 Règles suggérées",
                value="\n".join(f"{i+1}. {r}" for i, r in enumerate(rules[:5])),
                inline=False
            )
        if results["errors"]:
            success_embed.add_field(name="⚠️ Avertissements", value="\n".join(results["errors"][:3]), inline=False)
        user_data = get_user(author.id)
        footer = "Owner — Points illimités" if author.id == OWNER_ID else f"Points restants : {user_data['points']}"
        success_embed.set_footer(text=footer)
        await channel.send(embed=success_embed)

    except Exception as e:
        clear_session(author.id)
        err_embed = discord.Embed(
            title="❌ Erreur lors de la génération",
            description=f"`{e}`\n\nTes points n'ont pas été déduits. Réessaie avec `+generate` !",
            color=0xED4245
        )
        await channel.send(embed=err_embed)


# ─── COMMANDES UTILISATEUR ───────────────────────────────────────────────────
@bot.command(name="help")
async def cmd_help(ctx: commands.Context):
    embed = discord.Embed(
        title="📖 Aide — Discord Generator Bot",
        description="Bot propulsé par **Groq AI** pour créer des serveurs Discord complets automatiquement.",
        color=0x5865F2
    )
    embed.add_field(name="🌟 Commandes Utilisateurs", value=(
        "`+generate` — Lance la création IA de ton serveur Discord\n"
        "`+profile` — Voir tes points et invitations\n"
        "`+invites` — Voir ton nombre d'invitations\n"
        "`+help` — Afficher cette aide"
    ), inline=False)
    embed.add_field(name="👑 Commandes Owner", value=(
        "`+embed` — Poster l'embed de présentation du bot\n"
        "`+addpoints @user <n>` — Ajouter des points\n"
        "`+removepoints @user <n>` — Retirer des points\n"
        "`+setpoints @user <n>` — Définir les points\n"
        "`+addchannels @user <n>` — Ajouter des crédits salons\n"
        "`+userinfo @user` — Infos d'un utilisateur\n"
        "`+resetuser @user` — Réinitialiser un utilisateur\n"
        "`+listusers` — Liste tous les utilisateurs"
    ), inline=False)
    embed.add_field(name="🎫 Système d'accès", value=(
        f"• Rejoins le serveur officiel : {REQUIRED_GUILD_INVITE}\n"
        "• **1 invitation = 1 point = 1 génération**"
    ), inline=False)
    embed.add_field(name="⚙️ Comment ça marche ?", value=(
        "1. Rejoins le serveur officiel\n"
        "2. Invite des membres pour gagner des points\n"
        "3. Lance `+generate` sur ton serveur\n"
        "4. Réponds aux questions en DM\n"
        "5. Le serveur est créé automatiquement 🚀"
    ), inline=False)
    embed.set_footer(text="Propulsé par Groq AI • Llama 3.3 70B")
    await ctx.send(embed=embed)


@bot.command(name="profile")
async def cmd_profile(ctx: commands.Context):
    user = get_user(ctx.author.id)
    is_owner = ctx.author.id == OWNER_ID
    embed = discord.Embed(
        title=f"👤 Profil — {ctx.author.name}",
        color=0xFFD700 if is_owner else 0x5865F2
    )
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.add_field(name="🎫 Points", value=f"**{user['points']}**", inline=True)
    embed.add_field(name="📨 Invitations", value=f"**{user['invites']}**", inline=True)
    embed.add_field(name="🏗️ Générations", value=f"**{user['used_points']}**", inline=True)
    embed.add_field(name="👑 Statut", value="**Owner** 🌟" if is_owner else "**Membre**", inline=True)
    embed.set_footer(text="Invite des membres pour gagner des points !")
    await ctx.send(embed=embed)


@bot.command(name="invites")
async def cmd_invites(ctx: commands.Context):
    user = get_user(ctx.author.id)
    embed = discord.Embed(
        title="📨 Vos invitations",
        description=f"Tu as invité **{user['invites']}** personne(s).\n\n1 invitation = **1 point** = 1 génération supplémentaire !",
        color=0x57F287
    )
    embed.set_footer(text=f"Points actuels : {user['points']}")
    await ctx.send(embed=embed)


@bot.command(name="generate")
async def cmd_generate(ctx: commands.Context):
    if not ctx.guild:
        return await ctx.send("❌ Utilise cette commande dans un serveur Discord !")

    if not ctx.author.guild_permissions.administrator and ctx.author.id != OWNER_ID:
        embed = discord.Embed(
            title="❌ Permission refusée",
            description="Tu dois être **Administrateur** pour utiliser `+generate` !",
            color=0xED4245
        )
        return await ctx.send(embed=embed)

    if not await is_on_required_guild(ctx.author.id):
        embed = discord.Embed(
            title="🔒 Accès refusé",
            description=f"Tu dois être membre du serveur officiel !\n\n📎 **Rejoins ici :** {REQUIRED_GUILD_INVITE}",
            color=0xED4245
        )
        return await ctx.send(embed=embed)

    user = get_user(ctx.author.id)
    if user["points"] <= 0 and ctx.author.id != OWNER_ID:
        embed = discord.Embed(
            title="💸 Pas assez de points",
            description=f"Tu n'as pas de points disponibles !\n\nInvite des membres sur {REQUIRED_GUILD_INVITE}\n**1 invitation = 1 point**\n\nPoints actuels : **{user['points']}**",
            color=0xFEE75C
        )
        return await ctx.send(embed=embed)

    if get_session(ctx.author.id):
        embed = discord.Embed(
            title="⚠️ Session en cours",
            description="Tu as déjà une session active dans tes DMs !",
            color=0xFEE75C
        )
        return await ctx.send(embed=embed)

    set_session(ctx.author.id, {
        "guild_id": ctx.guild.id,
        "step": 0,
        "answers": {}
    })

    try:
        welcome = discord.Embed(
            title="🚀 Création de Serveur Discord — Groq AI",
            description=(
                f"Salut **{ctx.author.name}** ! 👋\n\n"
                f"Je vais créer un serveur Discord **complet et personnalisé** grâce à l'IA.\n\n"
                f"📋 Je vais te poser **{len(QUESTIONS)} questions** — réponds simplement dans ce DM !\n\n"
                f"⚠️ **La génération va supprimer et recréer** tous les salons et rôles de ton serveur.\n\n"
                f"✅ Points : **{'∞ (Owner)' if ctx.author.id == OWNER_ID else user['points']}**"
            ),
            color=0x5865F2
        )
        welcome.set_footer(text=f"Question 1/{len(QUESTIONS)}")
        await ctx.author.send(embed=welcome)

        _, first_q = QUESTIONS[0]
        q_embed = discord.Embed(
            title=f"Question 1/{len(QUESTIONS)}",
            description=first_q,
            color=0x5865F2
        )
        q_embed.set_footer(text="Réponds dans ce DM pour continuer...")
        await ctx.author.send(embed=q_embed)

        confirm = discord.Embed(
            title="📬 Questionnaire envoyé !",
            description="Vérifie tes **messages privés** ! 🎉",
            color=0x57F287
        )
        await ctx.send(embed=confirm)

    except discord.Forbidden:
        clear_session(ctx.author.id)
        embed = discord.Embed(
            title="❌ Impossible d'envoyer un DM",
            description="Active les messages privés dans tes paramètres Discord !",
            color=0xED4245
        )
        await ctx.send(embed=embed)


# ─── COMMANDE EMBED (Owner only) ─────────────────────────────────────────────
@bot.command(name="embed")
async def cmd_embed(ctx: commands.Context):
    if ctx.author.id != OWNER_ID:
        return await ctx.send("❌ Commande réservée au Owner.")

    # Supprimer le message de commande
    try:
        await ctx.message.delete()
    except Exception:
        pass

    # Embed principal de présentation
    main_embed = discord.Embed(
        title="🤖 Discord Server Generator — Powered by Groq AI",
        description=(
            "Crée un serveur Discord **complet et personnalisé** en quelques minutes grâce à l'intelligence artificielle !\n\n"
            "Notre bot analyse tes besoins et génère automatiquement :\n"
            "✅ Des **catégories** et **salons** adaptés\n"
            "✅ Des **rôles** avec couleurs personnalisées\n"
            "✅ Un **message de bienvenue** unique\n"
            "✅ Des **règles** adaptées à ton serveur\n\n"
            "🧠 Propulsé par **Llama 3.3 70B** via Groq AI"
        ),
        color=0x5865F2
    )
    main_embed.set_thumbnail(url=bot.user.display_avatar.url)
    main_embed.add_field(
        name="🎫 Comment obtenir des points ?",
        value=(
            f"1️⃣ Rejoins le serveur officiel → {REQUIRED_GUILD_INVITE}\n"
            "2️⃣ Invite des membres avec ton lien\n"
            "3️⃣ **1 invitation = 1 point = 1 génération**"
        ),
        inline=False
    )
    main_embed.add_field(
        name="🚀 Comment générer ton serveur ?",
        value=(
            "1️⃣ Ajoute le bot sur ton serveur\n"
            "2️⃣ Tape `+generate` en tant qu'administrateur\n"
            "3️⃣ Réponds aux **7 questions** en DM\n"
            "4️⃣ Le bot construit tout automatiquement ! 🎉"
        ),
        inline=False
    )
    main_embed.add_field(
        name="📋 Commandes disponibles",
        value=(
            "`+generate` — Lancer la création de serveur\n"
            "`+profile` — Voir tes points\n"
            "`+invites` — Voir tes invitations\n"
            "`+help` — Aide complète"
        ),
        inline=False
    )
    main_embed.set_footer(text="Discord Server Generator • Groq AI • Llama 3.3 70B")

    await ctx.send(embed=main_embed)

    # Embed secondaire avec les questions posées
    questions_embed = discord.Embed(
        title="❓ Les questions posées lors de la génération",
        description="Voici un aperçu des **7 questions** que le bot te posera en DM :",
        color=0x57F287
    )
    for i, (_, question_text) in enumerate(QUESTIONS):
        # Extraire juste la première ligne (titre de la question)
        first_line = question_text.split("\n")[0]
        questions_embed.add_field(
            name=f"Question {i+1}",
            value=first_line,
            inline=False
        )
    questions_embed.set_footer(text=f"Rejoins le serveur officiel pour commencer → {REQUIRED_GUILD_INVITE}")

    await ctx.send(embed=questions_embed)


# ─── COMMANDES OWNER ─────────────────────────────────────────────────────────
def owner_only():
    async def predicate(ctx):
        return ctx.author.id == OWNER_ID
    return commands.check(predicate)


@bot.command(name="addpoints")
@owner_only()
async def cmd_addpoints(ctx, member: discord.Member, amount: int):
    user = get_user(member.id)
    update_user(member.id, points=user["points"] + amount)
    embed = discord.Embed(
        title="✅ Points ajoutés",
        description=f"**+{amount}** points ajoutés à **{member.name}**\nTotal : **{user['points'] + amount}**",
        color=0x57F287
    )
    await ctx.send(embed=embed)


@bot.command(name="removepoints")
@owner_only()
async def cmd_removepoints(ctx, member: discord.Member, amount: int):
    user = get_user(member.id)
    new = max(0, user["points"] - amount)
    update_user(member.id, points=new)
    embed = discord.Embed(
        title="✅ Points retirés",
        description=f"**-{amount}** points retirés à **{member.name}**\nTotal : **{new}**",
        color=0xFEE75C
    )
    await ctx.send(embed=embed)


@bot.command(name="setpoints")
@owner_only()
async def cmd_setpoints(ctx, member: discord.Member, amount: int):
    update_user(member.id, points=amount)
    embed = discord.Embed(
        title="✅ Points définis",
        description=f"Points de **{member.name}** définis à **{amount}**",
        color=0x5865F2
    )
    await ctx.send(embed=embed)


@bot.command(name="addchannels")
@owner_only()
async def cmd_addchannels(ctx, member: discord.Member, amount: int):
    user = get_user(member.id)
    update_user(member.id, points=user["points"] + amount)
    embed = discord.Embed(
        title="✅ Crédits ajoutés",
        description=f"**+{amount}** crédits salons ajoutés à **{member.name}**",
        color=0x57F287
    )
    await ctx.send(embed=embed)


@bot.command(name="userinfo")
@owner_only()
async def cmd_userinfo(ctx, member: discord.Member):
    user = get_user(member.id)
    embed = discord.Embed(
        title=f"ℹ️ Info — {member.name}",
        color=0x5865F2
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=str(member.id), inline=True)
    embed.add_field(name="Points", value=str(user["points"]), inline=True)
    embed.add_field(name="Invitations", value=str(user["invites"]), inline=True)
    embed.add_field(name="Générations", value=str(user["used_points"]), inline=True)
    await ctx.send(embed=embed)


@bot.command(name="resetuser")
@owner_only()
async def cmd_resetuser(ctx, member: discord.Member):
    update_user(member.id, points=0, invites=0, used_points=0)
    embed = discord.Embed(
        title="🔄 Utilisateur réinitialisé",
        description=f"Les données de **{member.name}** ont été réinitialisées.",
        color=0xED4245
    )
    await ctx.send(embed=embed)


@bot.command(name="listusers")
@owner_only()
async def cmd_listusers(ctx):
    data = load_data()
    users = list(data["users"].items())
    if not users:
        return await ctx.send("Aucun utilisateur enregistré.")

    lines = []
    for uid, udata in users[:20]:
        try:
            user = await bot.fetch_user(int(uid))
            name = user.name
        except Exception:
            name = uid
        lines.append(f"**{name}** — {udata['points']} pts | {udata['invites']} invites")

    embed = discord.Embed(
        title=f"👥 Utilisateurs ({len(users)} total)",
        description="\n".join(lines),
        color=0x5865F2
    )
    embed.set_footer(text="Max 20 affichés")
    await ctx.send(embed=embed)


@cmd_addpoints.error
@cmd_removepoints.error
@cmd_setpoints.error
@cmd_addchannels.error
@cmd_userinfo.error
@cmd_resetuser.error
@cmd_listusers.error
async def owner_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("❌ Commande réservée au Owner.")


# ─── LANCEMENT ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
