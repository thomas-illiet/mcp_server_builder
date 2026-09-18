"""Canonical architecture and safety guide embedded in generated projects."""

from mcp_builder import BUILDER_VERSION, FASTMCP_VERSION, SCHEMA_VERSION

GUIDE = f"""# Guide MCP Builder

Ce projet cible exclusivement **FastMCP {FASTMCP_VERSION}**.

## Architecture obligatoire

- Placez les tools dans `app/tools/`, avec exactement un tool public par fichier.
- Placez les resources dans `app/resources/` et les prompts dans `app/prompts/`.
- Enregistrez explicitement chaque module depuis le `__init__.py` de son dossier ; aucune
  découverte dynamique ni import construit à l'exécution.
- Utilisez des signatures typées, des descriptions précises et des modèles Pydantic pour
  toute entrée complexe. Préférez les sorties structurées et typées.

Un tool exécute une action demandée par le modèle. Une resource expose des données adressables
par URI. Un prompt fournit un gabarit de message réutilisable.

## Erreurs, sécurité et annotations

- Signalez les erreurs corrigeables par l'utilisateur avec `fastmcp.exceptions.ToolError`.
- Ne placez jamais de secret dans les arguments, résultats ou logs.
- N'exécutez pas de code fourni par un utilisateur et validez tous les chemins et tailles.
- Documentez les annotations MCP pertinentes : lecture seule, idempotence et caractère
  destructif. Ne déclarez une propriété que si le comportement réel la respecte.
- Les opérations réseau générées doivent être asynchrones. Les fonctions synchrones sont
  adaptées aux calculs courts et FastMCP les exécute dans son pool de threads.

## Tests

Écrivez un test ciblé par composant avec `fastmcp.Client` et le serveur en mémoire. Vérifiez la
découverte, la validation des arguments, le résultat structuré et les erreurs utilisateur.
Les squelettes générés contiennent un `TODO` qui échoue explicitement : remplacez-le par la
logique métier et adaptez le test avant de considérer le composant fonctionnel.

Pour modifier un projet existant, appelez d'abord `inspect_project`, puis
`review_project_security` et `propose_project_patch`. Une proposition n'est jamais appliquée
par le serveur. Avant toute écriture côté client, vérifiez que `original_sha256` correspond
encore exactement au contenu du fichier local afin de ne pas écraser une modification récente.

Références :

- https://gofastmcp.com/servers/tools
- https://gofastmcp.com/servers/resources
- https://gofastmcp.com/servers/prompts
- https://gofastmcp.com/servers/testing
- https://modelcontextprotocol.io/specification/draft/server/index
"""


def get_builder_guide() -> dict:
    """Return the canonical guide and its machine-readable architecture rules."""
    return {
        "schema_version": SCHEMA_VERSION,
        "generator_version": BUILDER_VERSION,
        "guide": GUIDE,
        "fastmcp_version": FASTMCP_VERSION,
        "architecture_rules": [
            "app/tools contient exactement un fichier par tool public",
            "resources et prompts utilisent leurs primitives MCP dédiées",
            "les composants sont enregistrés explicitement depuis les __init__.py",
            "le code soumis n'est jamais exécuté par MCP Builder",
        ],
    }
