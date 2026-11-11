// remark-doku-links.mjs — schreibt Markdown-Verweise der Doku beim Website-Build auf Website-Seiten um
//
// Die Quelle docs/*.md (und CHANGELOG.md) bleibt GitHub-tauglich: sie verweist auf DATEI.md#anker,
// ../CHANGELOG.md, archive/…. scripts/sync-docs.sh kopiert sie nach src/content/docs/<slug>.md und
// schreibt die Slug-Liste nach src/doku-slugs.json ({"BERECHNUNGEN.md":"berechnungen", …}).
// Dieses Plugin (eingehängt in astro.config.mjs unter markdown.remarkPlugins) ändert jeden link-
// und definition-Knoten, dessen URL relativ ist und deren Pfadteil auf .md endet:
//   - Datei mit Website-Seite  → `${base}/${slug}/` + Anker
//   - Datei ohne Website-Seite → Quelle auf GitHub (blob/main/docs/<pfad> bzw. blob/main/<datei> für
//     Dateien im Repo-Wurzelverzeichnis wie ../CLAUDE.md), Anker bleibt
// Absolute URLs (http:, https:, mailto:, //…, /…) und reine Anker (#…) bleiben unangetastet; `eedc:`-Links (Schritte in
// der App, Lösungswege des Daten-Checkers) werden zu ihrem Text.
// Der Wächter scripts/check-links.mjs (postbuild) macht übrig gebliebene .md-Verweise rot.

const GITHUB_QUELLE = 'https://github.com/supernova1963/eedc-homeassistant/blob/main';
const NICHT_RELATIV = /^(?:[a-z][a-z0-9+.-]*:|\/|#)/i;

/**
 * Neues Ziel für eine Markdown-URL oder null (nicht anfassen).
 * @param {string} url
 * @param {{ base: string, slugs: Record<string,string>, quelleImRoot: boolean }} kontext
 */
export function dokuZiel(url, { base, slugs, quelleImRoot }) {
  if (typeof url !== 'string' || url === '' || NICHT_RELATIV.test(url)) return null;
  const schnitt = url.search(/[#?]/);
  let pfad = schnitt === -1 ? url : url.slice(0, schnitt);
  const rest = schnitt === -1 ? '' : url.slice(schnitt);
  if (!/\.md$/i.test(pfad)) return null;

  // ./, ../ und docs/ ablegen; imRoot merkt, ob der Rest im Repo-Wurzelverzeichnis liegt
  let imRoot = quelleImRoot;
  for (;;) {
    if (pfad.startsWith('./')) pfad = pfad.slice(2);
    else if (pfad.startsWith('../')) {
      pfad = pfad.slice(3);
      imRoot = true;
    } else if (pfad.startsWith('docs/')) {
      pfad = pfad.slice(5);
      imRoot = false;
    } else break;
  }

  const slug = Object.hasOwn(slugs, pfad) ? slugs[pfad] : null;
  if (slug) return `${base}/${slug}/${rest}`;
  return `${GITHUB_QUELLE}/${imRoot ? '' : 'docs/'}${pfad}${rest}`;
}

/**
 * @param {{ base: string, slugs: Record<string,string> }} optionen
 */
export default function remarkDokuLinks({ base, slugs }) {
  const basis = String(base ?? '').replace(/\/+$/, '');
  const changelogSlug = slugs['CHANGELOG.md'];

  return (tree, file) => {
    // CHANGELOG.md liegt im Repo-Wurzelverzeichnis, alle übrigen Quellen unter docs/
    const name = String(file?.path ?? '').split(/[\\/]/).pop() ?? '';
    const quelleImRoot = changelogSlug !== undefined && name.replace(/\.mdx?$/, '') === changelogSlug;
    const kontext = { base: basis, slugs, quelleImRoot };

    const besuche = (knoten) => {
      if ((knoten.type === 'link' || knoten.type === 'definition') && typeof knoten.url === 'string') {
        const neu = dokuZiel(knoten.url, kontext);
        if (neu !== null) knoten.url = neu;
      }
      if (Array.isArray(knoten.children)) {
        // E5 Daten-Checker: ein Schritt in eedc (`[Text](eedc:/einstellungen/…)`) navigiert nur in der App — auf der
        // Website bleibt sein Text stehen, der Link entfällt.
        knoten.children = knoten.children.flatMap((kind) =>
          kind.type === 'link' && typeof kind.url === 'string' && kind.url.startsWith('eedc:') ? kind.children : [kind]);
        knoten.children.forEach(besuche);
      }
    };
    besuche(tree);
  };
}
