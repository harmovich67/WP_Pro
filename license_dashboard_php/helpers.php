<?php
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

header('Content-Type: application/json; charset=utf-8');

function json_response($data, int $status = 200): void {
    http_response_code($status);
    echo json_encode($data);
    exit;
}

function read_json_body(): array {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function require_admin(): void {
    $headers = function_exists('getallheaders') ? getallheaders() : [];
    $auth = $headers['Authorization']
        ?? $headers['authorization']
        ?? ($_SERVER['HTTP_AUTHORIZATION'] ?? '');

    if ($auth !== 'Bearer ' . ADMIN_TOKEN) {
        json_response(['detail' => 'Unauthorized'], 401);
    }
}

function generate_license_key(string $tier): string {
    $prefixes = ['free' => 'HMF', 'basic' => 'HMB', 'pro' => 'HMP', 'enterprise' => 'HME'];
    $prefix = $prefixes[$tier] ?? 'HMP';

    $segments = [];
    for ($i = 0; $i < 4; $i++) {
        $segments[] = strtoupper(substr(bin2hex(random_bytes(4)), 0, 4));
    }

    return $prefix . '-' . implode('-', $segments);
}

function uuid4(): string {
    $data = random_bytes(16);
    $data[6] = chr((ord($data[6]) & 0x0f) | 0x40);
    $data[8] = chr((ord($data[8]) & 0x3f) | 0x80);
    return vsprintf('%s%s-%s-%s-%s-%s%s%s', str_split(bin2hex($data), 4));
}

// Convert a MySQL 'Y-m-d H:i:s' value to an ISO-8601 string matching Python's
// naive datetime.isoformat() (no timezone suffix) so the desktop app can parse it.
function iso(?string $mysqlDatetime): ?string {
    if (!$mysqlDatetime) {
        return null;
    }
    return str_replace(' ', 'T', $mysqlDatetime);
}

function now_mysql(): string {
    return gmdate('Y-m-d H:i:s');
}
