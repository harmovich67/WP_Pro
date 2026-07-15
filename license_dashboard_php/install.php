<?php
// One-time setup script: open this once in the browser after uploading
// (e.g. http://ser.42web.io/tafeal/install.php) to create the database tables,
// then delete this file from the server.

require_once __DIR__ . '/db.php';

header('Content-Type: text/plain; charset=utf-8');

try {
    $pdo->exec("CREATE TABLE IF NOT EXISTS licenses (
        id VARCHAR(36) PRIMARY KEY,
        license_key VARCHAR(64) UNIQUE NOT NULL,
        tier VARCHAR(20) DEFAULT 'basic',
        email VARCHAR(255) NULL,
        customer_name VARCHAR(255) NULL,
        whatsapp VARCHAR(50) NULL,
        created_at DATETIME NOT NULL,
        expires_at DATETIME NULL,
        is_active TINYINT(1) DEFAULT 1,
        max_activations INT DEFAULT 1,
        notes TEXT NULL,
        custom_features TEXT NULL,
        last_modified DATETIME NULL,
        INDEX (license_key),
        INDEX (email),
        INDEX (is_active)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");

    $pdo->exec("CREATE TABLE IF NOT EXISTS activations (
        id VARCHAR(36) PRIMARY KEY,
        license_id VARCHAR(36) NOT NULL,
        machine_id VARCHAR(255) NOT NULL,
        activated_at DATETIME NOT NULL,
        last_seen DATETIME NOT NULL,
        is_active TINYINT(1) DEFAULT 1,
        INDEX (license_id),
        INDEX (machine_id),
        INDEX (is_active),
        FOREIGN KEY (license_id) REFERENCES licenses(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");

    echo "Tables created successfully.\n";
    echo "IMPORTANT: delete install.php from the server now.\n";
} catch (PDOException $e) {
    http_response_code(500);
    echo "Setup failed: " . $e->getMessage() . "\n";
}
