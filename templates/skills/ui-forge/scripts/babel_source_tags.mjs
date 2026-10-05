import path from 'node:path';

function fnv1a(input) {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(36);
}

function jsxName(node) {
  if (!node) return '';
  if (node.type === 'JSXIdentifier') return node.name;
  if (node.type === 'JSXMemberExpression') return `${jsxName(node.object)}.${jsxName(node.property)}`;
  if (node.type === 'JSXNamespacedName') return `${jsxName(node.namespace)}:${jsxName(node.name)}`;
  return '';
}

function ownerName(openingPath) {
  const owner = openingPath.findParent((p) =>
    p.isFunctionDeclaration?.() ||
    p.isFunctionExpression?.() ||
    p.isArrowFunctionExpression?.() ||
    p.isClassMethod?.() ||
    p.isObjectMethod?.()
  );
  if (!owner) return 'module';
  if (owner.isFunctionDeclaration?.() && owner.node.id?.name) return owner.node.id.name;
  const parent = owner.parentPath;
  if (parent?.isVariableDeclarator?.() && parent.node.id?.name) return parent.node.id.name;
  if (parent?.isObjectProperty?.()) return parent.node.key?.name || parent.node.key?.value || 'objectMethod';
  if (owner.node.key?.name) return owner.node.key.name;
  return 'anonymous';
}

function hasAttribute(t, attributes, name) {
  return attributes.some((attr) => t.isJSXAttribute(attr) && t.isJSXIdentifier(attr.name, { name }));
}

export default function uiForgeSourceTags({ types: t }) {
  return {
    name: 'ui-forge-source-tags',
    pre() {
      this.uiForgeOrdinals = new Map();
    },
    visitor: {
      JSXOpeningElement(openingPath, state) {
        if (state.opts?.enabled === false) return;
        const tag = jsxName(openingPath.node.name);
        // DOM source tags are most reliable on intrinsic elements. Custom components may
        // swallow unknown props instead of forwarding them to a DOM node.
        if (!tag || tag[0] !== tag[0].toLowerCase() || tag.includes('.')) return;

        const attrs = openingPath.node.attributes;
        if (hasAttribute(t, attrs, 'data-ui-forge-source')) return;

        const filename = String(state.filename || 'unknown').replace(/\\/g, '/');
        const root = String(state.opts?.root || process.cwd()).replace(/\\/g, '/').replace(/\/$/, '');
        let relative = filename;
        if (filename.startsWith(`${root}/`)) relative = filename.slice(root.length + 1);
        else relative = path.posix.basename(filename);

        const owner = ownerName(openingPath);
        const ordinalKey = `${owner}:${tag}`;
        const ordinal = (this.uiForgeOrdinals.get(ordinalKey) || 0) + 1;
        this.uiForgeOrdinals.set(ordinalKey, ordinal);
        const stableId = `uif-${fnv1a(`${relative}|${owner}|${tag}|${ordinal}`)}`;
        const line = openingPath.node.loc?.start?.line || 0;
        const column = (openingPath.node.loc?.start?.column || 0) + 1;
        const source = `${relative}:${line}:${column}`;

        attrs.push(t.jsxAttribute(t.jsxIdentifier('data-ui-forge-id'), t.stringLiteral(stableId)));
        attrs.push(t.jsxAttribute(t.jsxIdentifier('data-ui-forge-source'), t.stringLiteral(source)));
      },
    },
  };
}
