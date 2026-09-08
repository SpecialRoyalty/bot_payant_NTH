# Bot Telegram VIP

Un bot pour **un seul groupe**, avec un panneau d’administration privé en français, entièrement piloté par boutons. Seuls les IDs numériques déclarés dans `ADMIN_IDS` peuvent le configurer.

## Ce qu’il fait

| Fonction | Comportement |
|---|---|
| Accès admin | Liste d’IDs autorisés dans `.env`, contrôlée à chaque action et chaque saisie. |
| Connexion au groupe | Boutons pour ajouter le bot, puis sélectionner un groupe où l’admin et le bot sont administrateurs. |
| Entrées et sorties | Suppression des messages de service annonçant les arrivées et départs dans le groupe connecté. |
| Publicité | Une photo, un texte et un bouton **VIP** ouvrant `https://t.me/pseudo`. |
| Première publication | Bouton **Publier / actualiser** : publication immédiate et activation du renouvellement. |
| Renouvellement | Toutes les **6 heures** après la dernière publication réussie : suppression de l’ancienne publicité, puis envoi de la nouvelle. |
| Ouverture ON, 01 h → 21 h | Groupe fermé aux membres non-admins. Un compte à rebours est publié puis remplacé chaque heure : « Le groupe ouvrira dans 20 heures » … « dans 1 heure ». |
| Ouverture ON, 21 h → 01 h | Groupe ouvert, compte à rebours supprimé et aucun message envoyé par le cycle d’ouverture. |
| Ouverture OFF | Automatisme arrêté, compte à rebours supprimé et permissions normales restaurées immédiatement. |

La photo et le texte sont envoyés en privé après avoir appuyé sur leur bouton. Le bouton VIP porte toujours le libellé **VIP** ; sa destination se configure avec **Configurer le @pseudo VIP**. Le texte est en texte simple, sur plusieurs lignes si besoin, jusqu’à 1 024 caractères. Certains emojis comptent pour deux unités.

Le bouton **Ouverture** contrôle à la fois le compte à rebours et les permissions par défaut. Avant de fermer, le bot mémorise les permissions normales du groupe ; il les restaure exactement à 21 h ou lors du passage à OFF. La fermeture bloque les textes, médias, vidéos, notes vocales, fichiers, sondages, autocollants, bots intégrés, aperçus de liens, réactions, invitations et sujets pour les membres ordinaires. Comme les permissions par défaut de Telegram ne s’appliquent pas aux administrateurs, les administrateurs du groupe conservent leurs droits.

## Installation rapide avec Docker

Il faut Docker avec Compose, une connexion Internet et un serveur ou ordinateur qui reste allumé. Aucune adresse publique ni aucun port entrant ne sont nécessaires : le bot utilise le polling Telegram.

1. Dans Telegram, ouvrez le compte officiel [@BotFather](https://t.me/BotFather), utilisez `/newbot` et récupérez le token. Gardez-le privé.
2. Décompressez l’archive et ouvrez un terminal dans `telegram-vip-bot`.
3. Copiez `.env.example` vers `.env` :

   ```bash
   cp .env.example .env
   ```

4. Dans `.env`, remplacez les exemples par votre token et les IDs numériques des administrateurs :

   ```dotenv
   BOT_TOKEN=votre_token_BotFather
   ADMIN_IDS=votre_id_numerique,id_numerique_du_second_admin
   DATABASE_PATH=data/bot.sqlite3
   ```

   Pour un seul administrateur, indiquez un seul nombre, sans virgule. Remplacez tous les exemples. Les `@pseudos` ne conviennent pas pour `ADMIN_IDS`. Une personne non autorisée qui écrit en privé au bot reçoit son ID numérique, sans accès au panneau.

5. Lancez le bot :

   ```bash
   docker compose up -d --build
   ```

6. Ouvrez votre bot dans Telegram et appuyez sur **Démarrer**. Ensuite, utilisez les boutons.

La liste d’IDs se modifie dans `.env`, puis se recharge avec `docker compose up -d --force-recreate`. Elle n’est pas modifiable depuis le panneau.

## Première configuration dans Telegram

1. Appuyez sur **Connecter / changer de groupe**, puis **Ajouter le bot au groupe**.
2. Donnez au bot le rôle **administrateur** avec les droits **Supprimer les messages** et **Restreindre les membres**. Le compte humain qui effectue l’ajout doit figurer dans `ADMIN_IDS` ; effectuez cette opération avec ce compte, sans identité anonyme.
3. Revenez au panneau et appuyez sur **Choisir le groupe**, puis **Sélectionner mon groupe**, sous le champ de saisie. Le groupe doit déjà contenir le bot.
4. Configurez **Photo**, **Texte** et **Configurer le @pseudo VIP**.
5. Utilisez **Aperçu** pour vérifier la publicité et cliquer sur le bouton VIP. Le bot valide le format du pseudo ; vérifiez vous-même qu’il ouvre le bon compte.
6. Appuyez sur **Publier / actualiser**. La publicité est envoyée immédiatement, puis remplacée toutes les 6 heures.
7. Appuyez sur **Ouverture : OFF** pour passer à **ON** et activer le cycle quotidien fermeture/compte à rebours/ouverture.

Modifier une photo, un texte ou un pseudo enregistre la configuration pour la prochaine publication. Pour appliquer immédiatement les modifications au groupe, appuyez sur **Publier / actualiser** ; le délai de 6 heures repart de cette publication.

**Arrêter la publicité** stoppe ses envois et supprime la publicité courante. Un changement de groupe rouvre d’abord l’ancien groupe, nettoie ses messages suivis, puis désactive les deux automatismes ; réactivez-les dans le nouveau groupe. Le bot quitte un groupe auquel une personne hors de `ADMIN_IDS` vient de l’ajouter.

## Horaires et redémarrages

- Le fuseau est `Europe/Paris`, y compris les changements d’heure d’été et d’hiver. Le fuseau du serveur n’a pas d’importance.
- Les échéances sont vérifiées toutes les 5 secondes. Les actions peuvent donc arriver quelques secondes après l’horaire, selon la connexion et la réponse de Telegram.
- À 01 h, si ON est toujours actif, le bot mémorise les permissions alors en vigueur, ferme le groupe et publie « Le groupe ouvrira dans 20 heures. » À chaque nouvelle heure, il supprime l’ancien compte à rebours avant d’envoyer le nouveau. À 11 h, le texte indique par exemple « dans 10 heures » ; à 20 h, « dans 1 heure ».
- À 21 h, le bot restaure les permissions mémorisées et supprime le dernier compte à rebours. Entre 21 h et 01 h, le cycle d’ouverture ne publie rien et ne change aucune permission. La publicité indépendante peut toutefois continuer selon son délai de 6 heures.
- Activer ON entre 01 h et 21 h ferme le groupe et affiche immédiatement le compte à rebours de l’heure en cours. L’activer entre 21 h et 01 h laisse le groupe ouvert et silencieux jusqu’à 01 h.
- OFF rouvre toujours le groupe et supprime le compte à rebours. ON reste actif d’un jour à l’autre jusqu’à ce qu’un admin l’arrête.
- Les réglages, permissions à restaurer, créneau horaire, IDs des messages et suppressions en attente sont stockés dans SQLite. Après un redémarrage, le bot se resynchronise avec le créneau courant sans publier les heures manquées.
- Si une réouverture ou une suppression échoue, l’état nécessaire est conservé, le panneau affiche une erreur et le bot réessaie. Une ancienne publicité ou un ancien compte à rebours impossible à supprimer bloque son remplacement pour éviter leur accumulation.

Le serveur doit fonctionner pour agir exactement à l’heure. Après une panne, le bot applique dès son retour l’état correspondant à l’heure de Paris. Telegram limite normalement la suppression aux messages de moins de **48 heures**. Une très longue panne peut imposer un nettoyage manuel : supprimez vous-même le message bloquant dans le groupe, puis actualisez le panneau. Les messages de service déjà absents des mises à jour Telegram ne peuvent pas être récupérés rétroactivement.

Ne retirez pas au bot son droit **Restreindre les membres** pendant que le groupe est fermé : sans ce droit, il ne peut pas restaurer automatiquement les permissions. Dans ce cas, redonnez-lui ce droit ou rouvrez manuellement le groupe. Si vous changez manuellement les permissions pendant la fermeture, le bot restaurera à 21 h la copie qu’il avait mémorisée au début de cette fermeture.

Comme toute application utilisant cette API, une coupure exactement entre l’envoi accepté par Telegram et la mémorisation locale de son ID peut laisser un message non suivi. Le code ne promet pas de transaction atomique entre Telegram et SQLite.

## Gestion du serveur

```bash
# Consulter les journaux
docker compose logs -f --tail=100

# Redémarrer
docker compose restart

# Arrêter en conservant les données
docker compose down
```

Ne lancez **qu’une seule instance** par token et par base SQLite. Le volume Docker `bot_data` conserve les réglages. N’utilisez pas `docker compose down -v` si vous souhaitez les conserver. Gardez une sauvegarde du volume lors d’un changement de serveur.

Le token ne doit pas être partagé ni ajouté à un dépôt public. Si vous changez complètement de bot/token, repartez d’une nouvelle base : les `file_id` des photos sont propres au bot.

## Installation sans Docker

Avec Python **3.11 ou supérieur**, depuis le dossier du projet, créez `.env` comme décrit ci-dessus, puis :

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python bot.py
```

Sur Windows, activez l’environnement avec `.venv\Scripts\Activate.ps1` dans PowerShell. Pour un fonctionnement permanent, utilisez un service système ou l’installation Docker. Le package `tzdata` fournit notamment le fuseau Paris sur Windows.

## Validation fournie

**21 tests du moteur réussis**, avec une fausse API Telegram : accès par ID, URL VIP, publicité à 6 heures, fermeture à 01 h, compte à rebours remplacé chaque heure, ouverture à 21 h, silence jusqu’à 01 h, ON/OFF, restauration exacte des permissions, fuseau Paris été/hiver, reprise après redémarrage, absence de doublons et nouvelles tentatives après erreur.

```bash
python3 -m unittest discover -s tests -v
```

Ces tests du moteur n’ont pas besoin du SDK Telegram, d’un token ni d’Internet. La syntaxe des fichiers Python a également été vérifiée. L’installation du SDK était indisponible dans l’environnement de création : le démarrage avec `python-telegram-bot` et les échanges avec un vrai groupe n’ont donc pas été exécutés ici. Le projet doit encore être configuré et lancé avec vos identifiants.

Après lancement, vérifiez dans un groupe de test : aperçu et destination VIP, publication puis remplacement manuel, suppression d’une entrée/sortie, accès refusé avec un compte hors liste, fermeture ON, impossibilité d’envoyer avec un compte membre, réouverture OFF et restauration des permissions habituelles. Pour tester les frontières 01 h et 21 h sans attendre, utilisez temporairement un environnement de test plutôt que votre groupe principal.

## Références techniques

- [Création d’un bot et BotFather — Telegram](https://core.telegram.org/bots/features#botfather)
- [Droits et limites de suppression — Telegram Bot API](https://core.telegram.org/bots/api#deletemessage)
- [Permissions par défaut et droit de restriction — Telegram Bot API](https://core.telegram.org/bots/api#setchatpermissions)
- [Sélection d’un groupe par bouton — python-telegram-bot](https://docs.python-telegram-bot.org/en/stable/telegram.keyboardbuttonrequestchat.html)
- [Planification — python-telegram-bot JobQueue](https://docs.python-telegram-bot.org/en/stable/telegram.ext.jobqueue.html)
