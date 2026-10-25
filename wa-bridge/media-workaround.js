const fs = require('fs');
const path = require('path');

const FIX = `        if (message.__x_id) {
            delete message.__x_id;
        }`;
const INSERT_BEFORE = "        // Bot's won't reply if canonicalUrl is set (linking)";

function patchSource(source) {
  if (source.includes(FIX)) return source;
  if (source.split(INSERT_BEFORE).length !== 2) {
    throw new Error('Unrecognized whatsapp-web.js Utils.js; cannot apply the media send compatibility fix');
  }
  return source.replace(INSERT_BEFORE, `${FIX}\n${INSERT_BEFORE}`);
}

function applyMediaFix(packageRoot = path.join(__dirname, 'node_modules', 'whatsapp-web.js')) {
  const utilsPath = path.join(packageRoot, 'src', 'util', 'Injected', 'Utils.js');
  let source;
  try {
    source = fs.readFileSync(utilsPath, 'utf8');
  } catch (error) {
    throw new Error(`Cannot read whatsapp-web.js internals at ${utilsPath}: ${error.message}`);
  }
  const patched = patchSource(source);
  if (patched !== source) {
    try {
      fs.writeFileSync(utilsPath, patched);
    } catch (error) {
      throw new Error(`Cannot apply whatsapp-web.js media send compatibility fix: ${error.message}`);
    }
    console.warn('Applied whatsapp-web.js media-send compatibility fix.');
  }
}

module.exports = { applyMediaFix, patchSource };
