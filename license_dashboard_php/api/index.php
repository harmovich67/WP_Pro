<?php
require_once __DIR__ . '/../config.php';
require_once __DIR__ . '/../db.php';
require_once __DIR__ . '/../helpers.php';

$scriptDir = rtrim(dirname($_SERVER['SCRIPT_NAME']), '/'); // .../tafeal/api
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$path = trim(substr($path, strlen($scriptDir)), '/');
$segments = $path === '' ? [] : explode('/', $path);
$method = $_SERVER['REQUEST_METHOD'];

function license_row_to_response(PDO $pdo, array $row): array {
    $stmt = $pdo->prepare('SELECT COUNT(*) FROM activations WHERE license_id = ? AND is_active = 1');
    $stmt->execute([$row['id']]);
    $activeCount = (int)$stmt->fetchColumn();

    return [
        'id' => $row['id'],
        'key' => $row['license_key'],
        'tier' => $row['tier'],
        'email' => $row['email'],
        'customer_name' => $row['customer_name'],
        'whatsapp' => $row['whatsapp'],
        'created_at' => iso($row['created_at']),
        'expires_at' => iso($row['expires_at']),
        'is_active' => (bool)$row['is_active'],
        'max_activations' => (int)$row['max_activations'],
        'current_activations' => $activeCount,
        'notes' => $row['notes'],
        'custom_features' => $row['custom_features'] ? json_decode($row['custom_features']) : new stdClass(),
        'last_modified' => iso($row['last_modified']),
    ];
}

// ---- GET /api/stats ----
if ($segments === ['stats'] && $method === 'GET') {
    require_admin();

    $total = (int)$pdo->query('SELECT COUNT(*) FROM licenses')->fetchColumn();
    $active = (int)$pdo->query('SELECT COUNT(*) FROM licenses WHERE is_active = 1')->fetchColumn();

    $stmt = $pdo->prepare('SELECT COUNT(*) FROM licenses WHERE expires_at IS NOT NULL AND expires_at < ?');
    $stmt->execute([now_mysql()]);
    $expired = (int)$stmt->fetchColumn();

    $byTier = [];
    foreach (['free', 'basic', 'pro', 'enterprise'] as $tier) {
        $stmt = $pdo->prepare('SELECT COUNT(*) FROM licenses WHERE tier = ?');
        $stmt->execute([$tier]);
        $byTier[$tier] = (int)$stmt->fetchColumn();
    }

    json_response([
        'total_licenses' => $total,
        'active_licenses' => $active,
        'expired_licenses' => $expired,
        'by_tier' => $byTier,
    ]);
}

// ---- GET /api/licenses (list) ----
if ($segments === ['licenses'] && $method === 'GET') {
    require_admin();

    $skip = isset($_GET['skip']) ? (int)$_GET['skip'] : 0;
    $limit = isset($_GET['limit']) ? (int)$_GET['limit'] : 50;
    $tier = $_GET['tier'] ?? null;
    $isActive = isset($_GET['is_active']) ? filter_var($_GET['is_active'], FILTER_VALIDATE_BOOLEAN) : null;
    $search = $_GET['search'] ?? null;

    $where = [];
    $params = [];
    if ($tier) {
        $where[] = 'tier = ?';
        $params[] = $tier;
    }
    if ($isActive !== null) {
        $where[] = 'is_active = ?';
        $params[] = $isActive ? 1 : 0;
    }
    if ($search) {
        $where[] = '(license_key LIKE ? OR email LIKE ? OR customer_name LIKE ?)';
        $like = "%$search%";
        array_push($params, $like, $like, $like);
    }

    $sql = 'SELECT * FROM licenses';
    if ($where) {
        $sql .= ' WHERE ' . implode(' AND ', $where);
    }
    // LIMIT/OFFSET are cast to int above, so interpolating them directly is safe
    // and avoids MySQL rejecting string-bound params for these clauses.
    $sql .= " ORDER BY created_at DESC LIMIT $limit OFFSET $skip";

    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);

    json_response(array_map(
        fn($r) => license_row_to_response($pdo, $r),
        $stmt->fetchAll()
    ));
}

// ---- POST /api/licenses (create) ----
if ($segments === ['licenses'] && $method === 'POST') {
    require_admin();

    $data = read_json_body();
    $tier = $data['tier'] ?? 'basic';
    $id = uuid4();
    $key = generate_license_key($tier);
    $now = now_mysql();

    $daysValid = array_key_exists('days_valid', $data) ? $data['days_valid'] : 30;
    $expiresAt = $daysValid ? gmdate('Y-m-d H:i:s', strtotime("+{$daysValid} days")) : null;
    $customFeatures = json_encode($data['custom_features'] ?? new stdClass());

    $stmt = $pdo->prepare(
        'INSERT INTO licenses
            (id, license_key, tier, email, customer_name, whatsapp, created_at, expires_at, is_active, max_activations, notes, custom_features, last_modified)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)'
    );
    $stmt->execute([
        $id, $key, $tier,
        $data['email'] ?? null,
        $data['customer_name'] ?? null,
        $data['whatsapp'] ?? null,
        $now, $expiresAt,
        $data['max_activations'] ?? 1,
        $data['notes'] ?? null,
        $customFeatures,
        $now,
    ]);

    $stmt = $pdo->prepare('SELECT * FROM licenses WHERE id = ?');
    $stmt->execute([$id]);
    json_response(license_row_to_response($pdo, $stmt->fetch()));
}

// ---- /api/licenses/{id} ----
if (count($segments) === 2 && $segments[0] === 'licenses') {
    $id = $segments[1];

    if ($method === 'GET') {
        require_admin();
        $stmt = $pdo->prepare('SELECT * FROM licenses WHERE id = ?');
        $stmt->execute([$id]);
        $row = $stmt->fetch();
        if (!$row) json_response(['detail' => 'License not found'], 404);
        json_response(license_row_to_response($pdo, $row));
    }

    if ($method === 'PUT') {
        require_admin();
        $stmt = $pdo->prepare('SELECT * FROM licenses WHERE id = ?');
        $stmt->execute([$id]);
        if (!$stmt->fetch()) json_response(['detail' => 'License not found'], 404);

        $data = read_json_body();
        $fields = ['tier', 'email', 'customer_name', 'whatsapp', 'is_active', 'expires_at', 'max_activations', 'notes', 'custom_features'];
        $sets = [];
        $params = [];
        foreach ($fields as $f) {
            if (!array_key_exists($f, $data)) continue;
            $sets[] = "$f = ?";
            if ($f === 'custom_features') {
                $params[] = json_encode($data[$f]);
            } elseif ($f === 'is_active') {
                $params[] = $data[$f] ? 1 : 0;
            } elseif ($f === 'expires_at') {
                $params[] = $data[$f] ? gmdate('Y-m-d H:i:s', strtotime($data[$f])) : null;
            } else {
                $params[] = $data[$f];
            }
        }
        $sets[] = 'last_modified = ?';
        $params[] = now_mysql();
        $params[] = $id;

        $stmt = $pdo->prepare('UPDATE licenses SET ' . implode(', ', $sets) . ' WHERE id = ?');
        $stmt->execute($params);

        $stmt = $pdo->prepare('SELECT * FROM licenses WHERE id = ?');
        $stmt->execute([$id]);
        json_response(license_row_to_response($pdo, $stmt->fetch()));
    }

    if ($method === 'DELETE') {
        require_admin();
        $stmt = $pdo->prepare('SELECT id FROM licenses WHERE id = ?');
        $stmt->execute([$id]);
        if (!$stmt->fetch()) json_response(['detail' => 'License not found'], 404);

        $pdo->prepare('DELETE FROM licenses WHERE id = ?')->execute([$id]);
        json_response(['message' => 'License deleted successfully']);
    }
}

// ---- GET /api/licenses/{id}/activations ----
if (count($segments) === 3 && $segments[0] === 'licenses' && $segments[2] === 'activations' && $method === 'GET') {
    require_admin();
    $id = $segments[1];

    $stmt = $pdo->prepare('SELECT id FROM licenses WHERE id = ?');
    $stmt->execute([$id]);
    if (!$stmt->fetch()) json_response(['detail' => 'License not found'], 404);

    $stmt = $pdo->prepare('SELECT * FROM activations WHERE license_id = ?');
    $stmt->execute([$id]);

    json_response(array_map(fn($a) => [
        'id' => $a['id'],
        'machine_id' => $a['machine_id'],
        'activated_at' => iso($a['activated_at']),
        'last_seen' => iso($a['last_seen']),
        'is_active' => (bool)$a['is_active'],
    ], $stmt->fetchAll()));
}

// ---- DELETE /api/activations/{id} ----
if (count($segments) === 2 && $segments[0] === 'activations' && $method === 'DELETE') {
    require_admin();
    $id = $segments[1];

    $stmt = $pdo->prepare('SELECT id FROM activations WHERE id = ?');
    $stmt->execute([$id]);
    if (!$stmt->fetch()) json_response(['detail' => 'Activation not found'], 404);

    $pdo->prepare('UPDATE activations SET is_active = 0 WHERE id = ?')->execute([$id]);
    json_response(['message' => 'Activation deactivated successfully']);
}

// ---- POST /api/verify (public, called by the desktop app) ----
if ($segments === ['verify'] && $method === 'POST') {
    $data = read_json_body();
    $licenseKey = $data['license_key'] ?? '';
    $machineId = $data['machine_id'] ?? '';

    $stmt = $pdo->prepare('SELECT * FROM licenses WHERE license_key = ?');
    $stmt->execute([$licenseKey]);
    $license = $stmt->fetch();

    if (!$license) {
        json_response(['success' => false, 'message' => 'مفتاح الترخيص غير صالح']);
    }

    $stmt = $pdo->prepare('SELECT * FROM activations WHERE license_id = ? AND machine_id = ?');
    $stmt->execute([$license['id'], $machineId]);
    $existing = $stmt->fetch();

    $now = now_mysql();

    if ($existing) {
        if ($license['expires_at'] && $license['expires_at'] < $now) {
            json_response(['success' => false, 'message' => 'الترخيص منتهي الصلاحية']);
        }
        if (!$license['is_active']) {
            $pdo->prepare('UPDATE licenses SET is_active = 1 WHERE id = ?')->execute([$license['id']]);
        }
        $pdo->prepare('UPDATE activations SET last_seen = ?, is_active = 1 WHERE id = ?')
            ->execute([$now, $existing['id']]);

        json_response([
            'success' => true,
            'tier' => $license['tier'],
            'expires_at' => iso($license['expires_at']),
            'custom_features' => $license['custom_features'] ? json_decode($license['custom_features']) : new stdClass(),
        ]);
    }

    if (!$license['is_active']) {
        json_response(['success' => false, 'message' => 'الترخيص معطل']);
    }
    if ($license['expires_at'] && $license['expires_at'] < $now) {
        json_response(['success' => false, 'message' => 'الترخيص منتهي الصلاحية']);
    }

    $stmt = $pdo->prepare('SELECT COUNT(*) FROM activations WHERE license_id = ? AND is_active = 1');
    $stmt->execute([$license['id']]);
    $activeCount = (int)$stmt->fetchColumn();

    if ($activeCount >= $license['max_activations']) {
        json_response([
            'success' => false,
            'message' => "تم استنفاد عدد التفعيلات المسموح ({$license['max_activations']})",
        ]);
    }

    $pdo->prepare(
        'INSERT INTO activations (id, license_id, machine_id, activated_at, last_seen, is_active) VALUES (?, ?, ?, ?, ?, 1)'
    )->execute([uuid4(), $license['id'], $machineId, $now, $now]);

    json_response([
        'success' => true,
        'tier' => $license['tier'],
        'expires_at' => iso($license['expires_at']),
        'custom_features' => $license['custom_features'] ? json_decode($license['custom_features']) : new stdClass(),
    ]);
}

// ---- POST /api/deactivate (public, called by the desktop app) ----
if ($segments === ['deactivate'] && $method === 'POST') {
    $data = read_json_body();
    $licenseKey = $data['license_key'] ?? '';
    $machineId = $data['machine_id'] ?? '';

    $stmt = $pdo->prepare('SELECT id FROM licenses WHERE license_key = ?');
    $stmt->execute([$licenseKey]);
    $license = $stmt->fetch();

    if (!$license) {
        json_response(['success' => false, 'message' => 'License not found']);
    }

    $pdo->prepare('UPDATE activations SET is_active = 0 WHERE license_id = ? AND machine_id = ?')
        ->execute([$license['id'], $machineId]);

    json_response(['success' => true, 'message' => 'Deactivated successfully']);
}

json_response(['detail' => 'Not found'], 404);
