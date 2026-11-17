# Déployer Permis Express sur Vercel

## 1. Mettre le projet en ligne
**Option A : ligne de commande** (Node.js requis)
```
npm i -g vercel
vercel login
vercel          (premier déploiement, répondez Entrée aux questions)
vercel --prod   (mise en production)
```
**Option B : GitHub** : créez un dépôt avec ce dossier, puis sur vercel.com > Add New > Project > importez le dépôt. Vercel détecte Flask tout seul.

## 2. Ajouter la base de données (obligatoire pour garder les comptes et réservations)
Vercel n'a pas de disque durable : sans base externe, les données disparaissent.
1. Projet Vercel > onglet **Storage** > **Create Database** > **Neon (Postgres)** > connecter au projet.
2. Vercel ajoute la variable `DATABASE_URL` automatiquement. Les tables se créent au premier chargement.

## 3. Clé secrète
Projet > Settings > Environment Variables > ajoutez `SECRET_KEY` avec une longue valeur aléatoire (30 caractères ou plus).

## 4. Redéployer
`vercel --prod` (ou Deployments > Redeploy). Ouvrez l'URL `https://votre-projet.vercel.app`.

## 5. Installer l'application sur smartphone
- **Android (Chrome)** : bouton « Installer l'application » en bas de page, ou menu ⋮ > Installer l'application.
- **iPhone (Safari)** : bouton Partager > Sur l'écran d'accueil.

## À modifier avant la mise en ligne
- Numéro, e-mail : `CONTACT` dans `app.py`.
- Adresses des agences : `templates/contact.html`.
- Photos : `public/static/img/` (photos fournies par vous ; à remplacer par des photos dont vous détenez les droits avant un usage commercial).
