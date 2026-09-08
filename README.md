# Bot Telegram VIP

Un bot pour **un seul groupe**, avec un panneau d’administration privé en français, entièrement piloté par boutons. Seuls les IDs numériques déclarés dans `ADMIN_IDS` peuvent le configurer.

## Ce qu’il fait

| Fonction | Comportement |
|---|---|
| Accès admin | Liste d’IDs autorisés dans `.env`, contrôlée à chaque action et chaque saisie. |
| Connexion au groupe | Détection automatique à l’ajout, groupes détectés sous forme de boutons, `/start` dans le groupe et saisie manuelle de l’ID en secours. |
| Diagnostic PostgreSQL | État visible dans le panneau et bouton effectuant une vraie requête de contrôle. |
| Entrées et sorties | Suppression des messages de service annonçant les arrivées et départs dans le groupe connecté. |
| Publicité | Une photo, un texte et un bouton **VIP** ouvrant `https://t.me/pseudo`. |
| Première publication | Bouton **Publier / actualiser** : publication immédiate et activation du renouvellement. |
| Renouvellement | Toutes les **6 heures** après la dernière publication réussie : suppression de l’ancienne publicité, puis envoi de la nouvelle. |
| Ouverture ON, 01 h → 21 h | Groupe fermé aux membres non-admins. Un compte à rebours est publié puis remplacé chaque heure : « Le groupe ouvrira dans 20 heures » … « dans 1 heure ». |
| Ouverture ON, 21 h → 01 h | Groupe ouvert, compte à rebours supprimé et aucun message envoyé par le cycle d’ouverture. |
| Ouverture OFF | Automatisme arrêté, compte à rebours supprimé et permissions normales restaurées immédiatement. |

La photo et le texte sont envoyés en privé après avoir appuyé sur leur bouton. Le bouton VIP porte toujours le libellé **VIP** ; sa destination se configure avec **Configurer le @pseudo VIP**. Le texte est en texte simple, sur plusieurs lignes si besoin, jusqu’à 1 024 caractères. Certains emojis comptent pour deux unités.

Le bouton **Ouverture** contrôle à la fois le compte à rebours et les permissions par défaut. Avant de fermer, le bot mémorise les permissions normales du groupe ; il les restaure exactement à 21 h ou lors du passage à OFF. La fermeture bloque les textes, médias, vidéos, notes vocales, fichiers, sondages, autocollants, bots intégrés, aperçus de liens, réactions, invitations et sujets pour les membres ordinaires. Comme les permissions par défaut de Telegram ne s’appliquent pas aux administrateurs, les administrateurs du groupe conservent leurs droits.

## Déploiement sur Railway

1. Créez un projet Railway et ajoutez un service **PostgreSQL**.
2. Ajoutez le code du bot comme second service dans le même projet.
3. Dans l’onglet **Variables** du service du bot, configurez :

   ```dotenv
   BOT_TOKEN=votre_token_BotFather
   ADMIN_IDS=votre_id_numerique,id_numerique_du_second_admin
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   ```

   `Postgres` doit être exactement le nom du service PostgreSQL sur votre canevas Railway. Si vous avez renommé ce service, adaptez la partie située avant `.DATABASE_URL`. La valeur `${{Postgres.DATABASE_URL}}` est une référence Railway : au démarrage, le programme reçoit la vraie URL privée de connexion.

4. Déployez les changements. Railway utilisera automatiquement le `Dockerfile`; aucune commande de démarrage supplémentaire n’est nécessaire.
5. Consultez les journaux du service du bot. Les lignes **« PostgreSQL connecté ; table bot_state prête »** puis **« Bot démarré »** confirment le démarrage. Ouvrez ensuite le bot dans Telegram et appuyez sur **Démarrer**.

Railway fournit `DATABASE_URL` avec son service PostgreSQL et permet de référencer une variable d’un autre service avec la syntaxe `${{SERVICE_NAME.VAR}}`. Ne copiez pas la vraie URL de la base dans le code ou dans un dépôt public.

## Installation locale avec Docker

Il faut Docker avec Compose, une connexion Internet et un serveur ou ordinateur qui reste allumé. Aucune adresse publique ni aucun port entrant ne sont nécessaires : le bot utilise le polling Telegram.

1. Dans Telegram, ouvrez le compte officiel [@BotFather](https://t.me/BotFather), utilisez `/newbot` et récupérez le token. Gardez-le privé.
2. Décompressez l’archive et ouvrez un terminal dans `telegram-vip-bot`.
3. Copiez `.env.local.example` vers `.env.local` :

   ```bash
   cp .env.local.example .env.local
   ```

4. Dans `.env.local`, remplacez le token et les IDs numériques. Le fichier Compose fournit lui-même l’URL du PostgreSQL local : n’ajoutez pas la référence Railway dans ce fichier.

   ```dotenv
   BOT_TOKEN=votre_token_BotFather
   ADMIN_IDS=votre_id_numerique,id_numerique_du_second_admin
   ```

   Pour un seul administrateur, indiquez un seul nombre, sans virgule. Remplacez tous les exemples. Les `@pseudos` ne conviennent pas pour `ADMIN_IDS`. Une personne non autorisée qui écrit en privé au bot reçoit son ID numérique, sans accès au panneau.

5. Lancez PostgreSQL et le bot :

   ```bash
   docker compose up -d --build
   ```

6. Ouvrez votre bot dans Telegram et appuyez sur **Démarrer**. Ensuite, utilisez les boutons.

La liste d’IDs se modifie dans `.env.local`, puis se recharge avec `docker compose up -d --force-recreate`. Elle n’est pas modifiable depuis le panneau.

## Connexion du groupe

1. Dans le panneau privé, appuyez sur **Connecter / changer de groupe**, puis **Ajouter le bot au groupe**.
2. Donnez au bot le rôle **administrateur** avec les droits **Supprimer les messages** et **Restreindre les membres**. Faites l’ajout avec un compte dont l’ID figure dans `ADMIN_IDS`.
3. Le bot connecte automatiquement le premier groupe valide et vous envoie le panneau en privé. Si un autre groupe est déjà connecté, le nouveau apparaît comme bouton **📍 Nom du groupe** dans **Connecter / changer de groupe**.

Si la détection ne se produit pas, utilisez l’un de ces deux secours :

- Dans le groupe, envoyez `/start@nom_de_votre_bot` avec le compte autorisé. Le bot vérifie les droits, connecte le groupe, supprime la commande et renvoie le panneau en privé.
- Dans le panneau, choisissez **Ajouter avec l’ID**, puis envoyez l’ID négatif du groupe, par exemple `-1001234567890`. Le bot et le compte autorisé doivent déjà être administrateurs du groupe.

Le bouton **Sélecteur Telegram** reste disponible, mais certains clients Telegram peuvent ne pas afficher correctement son clavier. Il n’est plus nécessaire. Si vous écrivez anonymement au nom du groupe, repassez temporairement sur votre identité personnelle pour `/start`, car le bot doit reconnaître votre ID autorisé.

## Première configuration de la publicité

1. Configurez **Photo**, **Texte** et **Configurer le @pseudo VIP**.
2. Utilisez **Aperçu** pour vérifier la publicité et cliquer sur le bouton VIP. Le bot valide le format du pseudo ; vérifiez vous-même qu’il ouvre le bon compte.
3. Appuyez sur **Publier / actualiser**. La publicité est envoyée immédiatement, puis remplacée toutes les 6 heures.
4. Appuyez sur **Ouverture : OFF** pour passer à **ON** et activer le cycle quotidien fermeture/compte à rebours/ouverture.

Modifier une photo, un texte ou un pseudo enregistre la configuration pour la prochaine publication. Pour appliquer immédiatement les modifications au groupe, appuyez sur **Publier / actualiser** ; le délai de 6 heures repart de cette publication.

**Arrêter la publicité** stoppe ses envois et supprime la publicité courante. Un changement de groupe rouvre d’abord l’ancien groupe, nettoie ses messages suivis, puis désactive les deux automatismes ; réactivez-les dans le nouveau groupe. Un ajout effectué par une personne hors de `ADMIN_IDS` reste passif : il ne connecte pas le groupe et ne donne aucun accès au panneau.

## Vérifier PostgreSQL

Le panneau affiche **PostgreSQL : ✅ connecté** après une opération réussie. Appuyez sur **Vérifier PostgreSQL** pour ouvrir une nouvelle connexion et exécuter une vraie requête `SELECT 1`. Le message **« PostgreSQL répond correctement »** confirme que `DATABASE_URL`, le réseau privé Railway et le service PostgreSQL fonctionnent au moment du test.

Si le bot ne démarre pas, recherchez dans les journaux **« Connexion PostgreSQL impossible »** et vérifiez que la variable du service bot est exactement `DATABASE_URL=${{Postgres.DATABASE_URL}}`, en adaptant `Postgres` si le service porte un autre nom. Le bot ne journalise jamais l’URL ni son mot de passe.

## Réduction maximale des coûts Railway

Cette version est optimisée pour rester disponible en permanence avec le moins d’activité possible :

- suppression de la vérification toutes les 5 secondes ; l’automatisation dort jusqu’à la prochaine heure, la prochaine publicité, une nouvelle tentative ou une modification admin ;
- aucune écriture PostgreSQL lorsque l’état JSON n’a pas changé ;
- connexion PostgreSQL courte uniquement lors d’un changement réel ou du diagnostic demandé ;
- long polling Telegram de 50 secondes pour réduire les requêtes à vide ;
- suppression de `APScheduler`, `pytz` et de l’option `job-queue` ;
- traitement séquentiel et petits pools HTTP adaptés à un seul groupe.

Sur Railway, gardez **une seule réplique**, ne créez pas de domaine public pour le bot et utilisez l’URL privée `${{Postgres.DATABASE_URL}}`. Configurez aussi une alerte et une **limite dure Compute Usage** dans la page Usage du workspace afin d’éviter une facture imprévue.

N’activez pas **Serverless/App Sleeping** pour ce bot : le polling Telegram et les actions programmées exigent que le processus reste vivant, et aucun appel HTTP entrant ne viendrait le réveiller à 01 h, 21 h ou lors d’une entrée dans le groupe. Railway facture l’usage réel du CPU, de la RAM, du stockage et du réseau ; un bot 24 h/24 et son service PostgreSQL conservent donc un coût de base. PostgreSQL est maintenu ici conformément à la configuration demandée. Pour descendre encore plus bas, il faudrait supprimer le service PostgreSQL et revenir à SQLite sur volume, ce qui constitue une autre architecture.

## Horaires et redémarrages

- Le fuseau est `Europe/Paris`, y compris les changements d’heure d’été et d’hiver. Le fuseau du serveur n’a pas d’importance.
- Le planificateur se réveille directement à la prochaine échéance. Les actions peuvent arriver quelques secondes après l’horaire selon la connexion, la réponse de Telegram ou un redémarrage Railway.
- À 01 h, si ON est toujours actif, le bot mémorise les permissions alors en vigueur, ferme le groupe et publie « Le groupe ouvrira dans 20 heures. » À chaque nouvelle heure, il supprime l’ancien compte à rebours avant d’envoyer le nouveau. À 11 h, le texte indique par exemple « dans 10 heures » ; à 20 h, « dans 1 heure ».
- À 21 h, le bot restaure les permissions mémorisées et supprime le dernier compte à rebours. Entre 21 h et 01 h, le cycle d’ouverture ne publie rien et ne change aucune permission. La publicité indépendante peut toutefois continuer selon son délai de 6 heures.
- Activer ON entre 01 h et 21 h ferme le groupe et affiche immédiatement le compte à rebours de l’heure en cours. L’activer entre 21 h et 01 h laisse le groupe ouvert et silencieux jusqu’à 01 h.
- OFF rouvre toujours le groupe et supprime le compte à rebours. ON reste actif d’un jour à l’autre jusqu’à ce qu’un admin l’arrête.
- Les réglages, permissions à restaurer, créneau horaire, IDs des messages et suppressions en attente sont stockés dans PostgreSQL, dans la table `bot_state`. Après un redémarrage, le bot se resynchronise avec le créneau courant sans publier les heures manquées.
- Si une réouverture ou une suppression échoue, l’état nécessaire est conservé, le panneau affiche une erreur et le bot réessaie. Une ancienne publicité ou un ancien compte à rebours impossible à supprimer bloque son remplacement pour éviter leur accumulation.

Le serveur doit fonctionner pour agir exactement à l’heure. Après une panne, le bot applique dès son retour l’état correspondant à l’heure de Paris. Telegram limite normalement la suppression aux messages de moins de **48 heures**. Une très longue panne peut imposer un nettoyage manuel : supprimez vous-même le message bloquant dans le groupe, puis actualisez le panneau. Les messages de service déjà absents des mises à jour Telegram ne peuvent pas être récupérés rétroactivement.

Ne retirez pas au bot son droit **Restreindre les membres** pendant que le groupe est fermé : sans ce droit, il ne peut pas restaurer automatiquement les permissions. Dans ce cas, redonnez-lui ce droit ou rouvrez manuellement le groupe. Si vous changez manuellement les permissions pendant la fermeture, le bot restaurera à 21 h la copie qu’il avait mémorisée au début de cette fermeture.

Comme toute application utilisant cette API, une coupure exactement entre l’envoi accepté par Telegram et la mémorisation locale de son ID peut laisser un message non suivi. Le code ne promet pas de transaction atomique entre Telegram et PostgreSQL.

## Gestion du serveur

```bash
# Consulter les journaux
docker compose logs -f --tail=100

# Redémarrer
docker compose restart

# Arrêter en conservant les données
docker compose down
```

Ne lancez **qu’une seule instance** du bot par token. Avec Docker Compose, le volume `postgres_data` conserve PostgreSQL. N’utilisez pas `docker compose down -v` si vous souhaitez garder les réglages. Sur Railway, activez les sauvegardes adaptées à votre projet PostgreSQL.

Cette version ne lit plus les anciennes bases SQLite. Lors du premier démarrage PostgreSQL, la table est créée automatiquement mais les anciens réglages SQLite ne sont pas importés : configurez de nouveau le groupe, la photo, le texte, le pseudo VIP et les boutons ON/OFF si vous aviez déjà lancé l’ancienne version.

Le token ne doit pas être partagé ni ajouté à un dépôt public. Si vous changez complètement de bot/token, repartez d’une nouvelle base : les `file_id` des photos sont propres au bot.

## Installation sans Docker

Avec Python **3.11 ou supérieur**, depuis le dossier du projet, créez manuellement `.env` avec `BOT_TOKEN`, `ADMIN_IDS` et une véritable URL PostgreSQL accessible depuis votre ordinateur. N’utilisez pas la référence `${{Postgres.DATABASE_URL}}` dans ce mode : elle n’est résolue que par Railway. Puis lancez :

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python bot.py
```

Sur Windows, activez l’environnement avec `.venv\Scripts\Activate.ps1` dans PowerShell. Pour un fonctionnement permanent, utilisez un service système ou l’installation Docker. Le package `tzdata` fournit notamment le fuseau Paris sur Windows.

## Validation fournie

**28 tests du moteur réussis**, avec une fausse API Telegram et une fausse connexion PostgreSQL : accès par ID, groupe manuel, groupes détectés, contrôle réel de connexion, absence d’écritures identiques ou de requêtes en période inactive, planification sans boucle, stockage JSONB paramétré, URL VIP, publicité à 6 heures, fermeture à 01 h, compte à rebours remplacé chaque heure, ouverture à 21 h, silence jusqu’à 01 h, ON/OFF, restauration exacte des permissions, fuseau Paris été/hiver, reprise après redémarrage, absence de doublons et nouvelles tentatives après erreur.

```bash
python3 -m unittest discover -s tests -v
```

Ces tests du moteur n’ont pas besoin du SDK Telegram, d’un token, d’Internet ni d’un serveur PostgreSQL. La syntaxe des fichiers Python a également été vérifiée. Les échanges avec un vrai groupe Telegram et une vraie base Railway n’ont pas été exécutés ici. Le projet doit encore être configuré et lancé avec vos identifiants.

Après lancement, vérifiez dans un groupe de test : aperçu et destination VIP, publication puis remplacement manuel, suppression d’une entrée/sortie, accès refusé avec un compte hors liste, fermeture ON, impossibilité d’envoyer avec un compte membre, réouverture OFF et restauration des permissions habituelles. Pour tester les frontières 01 h et 21 h sans attendre, utilisez temporairement un environnement de test plutôt que votre groupe principal.

## Références techniques

- [Création d’un bot et BotFather — Telegram](https://core.telegram.org/bots/features#botfather)
- [Droits et limites de suppression — Telegram Bot API](https://core.telegram.org/bots/api#deletemessage)
- [Permissions par défaut et droit de restriction — Telegram Bot API](https://core.telegram.org/bots/api#setchatpermissions)
- [Sélection d’un groupe par bouton — python-telegram-bot](https://docs.python-telegram-bot.org/en/stable/telegram.keyboardbuttonrequestchat.html)
- [Polling — python-telegram-bot](https://docs.python-telegram-bot.org/en/stable/telegram.ext.application.html#telegram.ext.Application.run_polling)
- [Variables de référence Railway](https://docs.railway.com/variables#reference-variables)
- [PostgreSQL et `DATABASE_URL` sur Railway](https://docs.railway.com/databases/postgresql#connect)
- [Tarification des ressources Railway](https://docs.railway.com/pricing/plans#resource-usage-pricing)
- [Limites de coût Railway](https://docs.railway.com/pricing/cost-control)
- [App Sleeping Railway](https://docs.railway.com/deployments/serverless)
