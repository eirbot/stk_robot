// mujoco_model.js — affiche un modèle MuJoCo (XML + maillages STL binaires) avec Three.js.
//
// Sert à la carte 3D (map.js) : la table et le robot viennent des modèles de vision_deporte
// (export Onshape, servis par la base sous /models/...), les mêmes que la simulation MuJoCo.
// Seules les géométries visuelles (class="visual") sont dessinées : maillages, boîtes,
// cylindres, sphères ; les matériaux donnent la couleur (rgba) ou une image (texture 2d).
//
//   EirbotMujoco.load('/models/table/table.xml').then(group => scene.add(group));
//
// Le groupe rendu est dans le repère du modèle, en mètres (comme MuJoCo).
(function (root) {
    // STL binaire (80 octets d'en-tête, nombre de triangles, puis 50 octets par triangle)
    function parseStl(buffer) {
        const view = new DataView(buffer);
        const count = view.getUint32(80, true);
        const positions = new Float32Array(count * 9);
        const normals = new Float32Array(count * 9);
        for (let i = 0; i < count; i++) {
            const o = 84 + i * 50;
            const n = [view.getFloat32(o, true), view.getFloat32(o + 4, true), view.getFloat32(o + 8, true)];
            for (let k = 0; k < 9; k++) {
                positions[i * 9 + k] = view.getFloat32(o + 12 + k * 4, true);
                normals[i * 9 + k] = n[k % 3];
            }
        }
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geo.setAttribute('normal', new THREE.BufferAttribute(normals, 3));
        return geo;
    }

    function nums(el, attr, def) {
        return (el.getAttribute(attr) || def).trim().split(/\s+/).map(Number);
    }

    // pos + quat MuJoCo (w x y z) -> objet Three.js
    function place(obj, el) {
        const p = nums(el, 'pos', '0 0 0');
        const q = nums(el, 'quat', '1 0 0 0');
        obj.position.set(p[0], p[1], p[2]);
        obj.quaternion.set(q[1], q[2], q[3], q[0]);
    }

    function baseName(file) {
        return file.split('/').pop().replace(/\.[^.]+$/, '');
    }

    async function load(url, options = {}) {
        const dir = url.slice(0, url.lastIndexOf('/') + 1);
        const xml = new DOMParser().parseFromString(await (await fetch(url)).text(), 'application/xml');
        const compiler = xml.querySelector('compiler');
        const meshDir = dir + ((compiler && compiler.getAttribute('meshdir')) ? compiler.getAttribute('meshdir') + '/' : '');

        // Ressources : maillages (nom = nom du fichier par défaut), textures, matériaux
        const meshFiles = {};
        xml.querySelectorAll('asset > mesh').forEach(m => {
            const file = m.getAttribute('file');
            meshFiles[m.getAttribute('name') || baseName(file)] = meshDir + file;
        });
        const textures = {};
        xml.querySelectorAll('asset > texture[file]').forEach(t => {
            textures[t.getAttribute('name')] = dir + t.getAttribute('file');
        });
        const materials = {};
        const textureLoader = new THREE.TextureLoader();
        xml.querySelectorAll('asset > material').forEach(m => {
            const rgba = nums(m, 'rgba', '0.7 0.7 0.7 1');
            const params = { color: new THREE.Color(rgba[0], rgba[1], rgba[2]), roughness: 0.7, metalness: 0.1 };
            if (rgba[3] < 1) Object.assign(params, { transparent: true, opacity: rgba[3] });
            const tex = textures[m.getAttribute('texture')];
            if (tex) params.map = textureLoader.load(tex);
            materials[m.getAttribute('name')] = new THREE.MeshStandardMaterial(params);
        });
        const defaultMaterial = new THREE.MeshStandardMaterial({ color: 0x888888, roughness: 0.7 });

        // Un fichier STL utilisé plusieurs fois n'est téléchargé qu'une fois
        const stlCache = {};
        const stl = name => stlCache[name] || (stlCache[name] = fetch(meshFiles[name])
            .then(r => { if (!r.ok) throw new Error(`${meshFiles[name]} : ${r.status}`); return r.arrayBuffer(); })
            .then(parseStl));

        const pending = [];
        function geomObject(g) {
            const type = g.getAttribute('type') || 'sphere';
            const size = nums(g, 'size', '0 0 0');
            const material = materials[g.getAttribute('material')] || defaultMaterial;
            const holder = new THREE.Group();
            place(holder, g);
            let geometry = null;
            if (type === 'box') geometry = new THREE.BoxGeometry(2 * size[0], 2 * size[1], 2 * size[2]);
            else if (type === 'sphere') geometry = new THREE.SphereGeometry(size[0], 16, 12);
            else if (type === 'cylinder') {
                geometry = new THREE.CylinderGeometry(size[0], size[0], 2 * size[1], 24);
                geometry.rotateX(Math.PI / 2);  // MuJoCo : axe Z ; Three.js : axe Y
            } else if (type === 'mesh' && meshFiles[g.getAttribute('mesh')]) {
                pending.push(stl(g.getAttribute('mesh')).then(geo => {
                    const mesh = new THREE.Mesh(geo, material);
                    mesh.castShadow = mesh.receiveShadow = !!options.shadows;
                    holder.add(mesh);
                }).catch(e => console.warn('[MUJOCO]', e.message)));
                return holder;
            }
            if (geometry) {
                const mesh = new THREE.Mesh(geometry, material);
                mesh.castShadow = mesh.receiveShadow = !!options.shadows;
                holder.add(mesh);
            }
            return holder;
        }

        function body(el) {
            const group = new THREE.Group();
            group.name = el.getAttribute('name') || '';
            place(group, el);
            for (const child of el.children) {
                if (child.tagName === 'geom' && child.getAttribute('class') === 'visual') group.add(geomObject(child));
                else if (child.tagName === 'body') group.add(body(child));
            }
            return group;
        }

        const model = new THREE.Group();
        xml.querySelectorAll('worldbody > body').forEach(b => model.add(body(b)));
        await Promise.all(pending);
        return model;
    }

    root.EirbotMujoco = { load, parseStl };
})(typeof window !== 'undefined' ? window : globalThis);
