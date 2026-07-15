# Requirements Document

## Introduction

نظام تحكم متكامل ومودرن لإدارة التراخيص (Integrated License Dashboard) مدمج بالكامل داخل تطبيق PyQt6 الرئيسي. يوفر النظام واجهة مستخدم حديثة وسهلة الاستخدام لإدارة التراخيص بشكل كامل، مع دعم جميع العمليات الأساسية من إنشاء وتعديل وحذف التراخيص، بالإضافة إلى عرض الإحصائيات والتقارير التفصيلية.

## Glossary

- **License_Dashboard**: نظام إدارة التراخيص المدمج داخل التطبيق الرئيسي
- **License_Manager**: المكون المسؤول عن إدارة منطق التراخيص والتحقق منها
- **Dashboard_Widget**: واجهة المستخدم الرسومية المدمجة في PyQt6
- **License_Record**: سجل ترخيص واحد يحتوي على جميع البيانات المرتبطة به
- **Admin_User**: المستخدم الإداري الذي يملك صلاحيات إدارة التراخيص
- **Activation**: عملية تفعيل ترخيص على جهاز معين
- **Machine_ID**: معرف فريد للجهاز المستخدم لربط الترخيص
- **License_Key**: مفتاح الترخيص الفريد المستخدم للتفعيل
- **Tier**: مستوى الترخيص (free, basic, pro, enterprise)
- **Backend_API**: واجهة برمجية خلفية لإدارة التراخيص (FastAPI)
- **Embedded_View**: عرض مدمج داخل التطبيق باستخدام QWebEngineView
- **Theme_System**: نظام الثيمات الموحد للتطبيق

## Requirements

### Requirement 1: Dashboard Integration

**User Story:** كمستخدم إداري، أريد الوصول إلى لوحة تحكم التراخيص من داخل التطبيق الرئيسي، حتى أتمكن من إدارة التراخيص بسهولة دون الحاجة لفتح تطبيق منفصل.

#### Acceptance Criteria

1. THE License_Dashboard SHALL be accessible as a new page in the main application sidebar
2. WHEN the Admin_User selects the dashboard page, THE Dashboard_Widget SHALL display the license management interface
3. THE Dashboard_Widget SHALL use QWebEngineView to embed the web-based dashboard interface
4. THE Dashboard_Widget SHALL maintain the same visual theme as the main application
5. THE Dashboard_Widget SHALL load the dashboard from the embedded Backend_API server
6. WHEN the application starts, THE Backend_API SHALL start automatically in the background
7. THE Backend_API SHALL run on a configurable local port (default: 8000)

### Requirement 2: License CRUD Operations

**User Story:** كمستخدم إداري، أريد إنشاء وتعديل وحذف التراخيص، حتى أتمكن من إدارة تراخيص العملاء بشكل كامل.

#### Acceptance Criteria

1. WHEN the Admin_User clicks "Create License", THE License_Dashboard SHALL display a creation form
2. THE creation form SHALL accept tier, customer name, email, WhatsApp number, validity period, max activations, and notes
3. WHEN the Admin_User submits the creation form with valid data, THE License_Manager SHALL generate a unique License_Key
4. THE License_Key SHALL follow the format: {TIER_PREFIX}-XXXX-XXXX-XXXX-XXXX
5. WHEN a License_Record is created, THE License_Manager SHALL store it in the database with creation timestamp
6. WHEN the Admin_User selects a License_Record, THE License_Dashboard SHALL display edit and delete options
7. WHEN the Admin_User updates a License_Record, THE License_Manager SHALL save the changes and update the last_modified timestamp
8. WHEN the Admin_User deletes a License_Record, THE License_Dashboard SHALL prompt for confirmation
9. IF the Admin_User confirms deletion, THEN THE License_Manager SHALL remove the License_Record and all associated Activation records

### Requirement 3: License Activation Management

**User Story:** كمستخدم إداري، أريد عرض وإدارة تفعيلات التراخيص، حتى أتمكن من مراقبة استخدام التراخيص والتحكم في التفعيلات.

#### Acceptance Criteria

1. WHEN the Admin_User views a License_Record, THE License_Dashboard SHALL display the current activation count and maximum allowed activations
2. THE License_Dashboard SHALL display a list of all active Activation records for each License_Record
3. FOR EACH Activation, THE License_Dashboard SHALL display Machine_ID, activation date, and last seen timestamp
4. WHEN the Admin_User clicks "Deactivate" on an Activation, THE License_Manager SHALL mark the Activation as inactive
5. WHEN an Activation is deactivated, THE License_Manager SHALL decrement the current activation count
6. THE License_Dashboard SHALL display a warning indicator WHEN current activations approach max_activations limit

### Requirement 4: Statistics and Reporting

**User Story:** كمستخدم إداري، أريد عرض إحصائيات شاملة عن التراخيص، حتى أتمكن من فهم حالة التراخيص واتخاذ قرارات مستنيرة.

#### Acceptance Criteria

1. THE License_Dashboard SHALL display total license count in a statistics card
2. THE License_Dashboard SHALL display active license count in a statistics card
3. THE License_Dashboard SHALL display expired license count in a statistics card
4. THE License_Dashboard SHALL display license count by Tier in separate statistics cards
5. THE statistics cards SHALL update in real-time WHEN license data changes
6. THE License_Dashboard SHALL display a table showing all License_Record entries with key information
7. THE table SHALL support sorting by creation date, expiration date, tier, and status
8. THE License_Dashboard SHALL calculate and display revenue metrics based on tier pricing

### Requirement 5: Search and Filtering

**User Story:** كمستخدم إداري، أريد البحث والفلترة في التراخيص، حتى أتمكن من العثور على تراخيص محددة بسرعة.

#### Acceptance Criteria

1. THE License_Dashboard SHALL provide a search input field
2. WHEN the Admin_User enters text in the search field, THE License_Dashboard SHALL filter License_Record entries by License_Key, customer name, or email
3. THE License_Dashboard SHALL provide filter options for Tier (free, basic, pro, enterprise)
4. THE License_Dashboard SHALL provide filter options for status (active, inactive, expired)
5. WHEN the Admin_User applies filters, THE License_Dashboard SHALL display only matching License_Record entries
6. THE License_Dashboard SHALL display the count of filtered results
7. THE License_Dashboard SHALL provide a "Clear Filters" button to reset all filters

### Requirement 6: Theme Integration

**User Story:** كمستخدم، أريد أن تتطابق لوحة التحكم مع ثيم التطبيق الرئيسي، حتى تكون التجربة متسقة وموحدة.

#### Acceptance Criteria

1. THE Dashboard_Widget SHALL detect the current Theme_System setting (dark/light)
2. WHEN the Theme_System is set to dark mode, THE License_Dashboard SHALL apply dark theme colors
3. WHEN the Theme_System is set to light mode, THE License_Dashboard SHALL apply light theme colors
4. THE License_Dashboard SHALL use the same color palette as defined in the Theme_System
5. WHEN the Admin_User changes the theme in the main application, THE License_Dashboard SHALL update its theme automatically
6. THE License_Dashboard SHALL use the same font family and sizes as the main application
7. THE License_Dashboard SHALL maintain consistent spacing, borders, and border-radius values with the main application

### Requirement 7: Backend API Integration

**User Story:** كمطور، أريد دمج Backend_API الموجود مع التطبيق الرئيسي، حتى يعمل النظام بشكل متكامل دون الحاجة لتشغيل خوادم منفصلة.

#### Acceptance Criteria

1. THE License_Dashboard SHALL start the Backend_API server as a background thread WHEN the application starts
2. THE Backend_API SHALL use the existing FastAPI implementation from license_dashboard/main.py
3. THE Backend_API SHALL connect to the same database used by the main application
4. THE Backend_API SHALL expose REST endpoints for all CRUD operations
5. THE Dashboard_Widget SHALL communicate with the Backend_API using HTTP requests
6. WHEN the application closes, THE License_Dashboard SHALL gracefully shutdown the Backend_API server
7. IF the Backend_API fails to start, THEN THE License_Dashboard SHALL display an error message and disable dashboard functionality
8. THE Backend_API SHALL require authentication using an admin token for all operations

### Requirement 8: Responsive Design

**User Story:** كمستخدم إداري، أريد واجهة مستخدم responsive، حتى تعمل بشكل جيد على أحجام نوافذ مختلفة.

#### Acceptance Criteria

1. THE License_Dashboard SHALL adapt its layout WHEN the window width is less than 1024 pixels
2. WHEN in narrow mode, THE statistics cards SHALL stack vertically instead of horizontally
3. THE License_Dashboard SHALL use horizontal scrolling for the license table WHEN the window is too narrow
4. THE License_Dashboard SHALL maintain readability at minimum window size of 800x600 pixels
5. THE License_Dashboard SHALL scale font sizes proportionally WHEN the window is resized
6. THE License_Dashboard SHALL hide non-essential columns in the table WHEN space is limited

### Requirement 9: WhatsApp Integration

**User Story:** كمستخدم إداري، أريد إرسال معلومات الترخيص للعملاء عبر WhatsApp، حتى أتمكن من التواصل معهم بسهولة.

#### Acceptance Criteria

1. WHEN a License_Record has a WhatsApp number, THE License_Dashboard SHALL display a WhatsApp button
2. WHEN the Admin_User clicks the WhatsApp button, THE License_Dashboard SHALL open WhatsApp Web with a pre-filled message
3. THE pre-filled message SHALL include the License_Key and welcome text
4. THE WhatsApp button SHALL be disabled IF the License_Record does not have a WhatsApp number
5. THE License_Dashboard SHALL validate WhatsApp numbers to ensure they are in international format

### Requirement 10: Error Handling and Validation

**User Story:** كمستخدم إداري، أريد رسائل خطأ واضحة وتحقق من البيانات، حتى أتجنب الأخطاء وأفهم المشاكل بسرعة.

#### Acceptance Criteria

1. WHEN the Admin_User submits invalid data, THE License_Dashboard SHALL display specific error messages
2. THE License_Dashboard SHALL validate that customer email is in valid email format
3. THE License_Dashboard SHALL validate that validity period is a positive integer
4. THE License_Dashboard SHALL validate that max_activations is at least 1
5. WHEN the Backend_API is unreachable, THE License_Dashboard SHALL display a connection error message
6. WHEN a database error occurs, THE License_Manager SHALL log the error and display a user-friendly message
7. THE License_Dashboard SHALL prevent duplicate License_Key generation by checking existing keys

### Requirement 11: Performance and Optimization

**User Story:** كمستخدم إداري، أريد أداء سريع ومستجيب، حتى أتمكن من العمل بكفاءة دون تأخير.

#### Acceptance Criteria

1. THE License_Dashboard SHALL load the initial view within 2 seconds
2. THE License_Dashboard SHALL update statistics within 500 milliseconds WHEN data changes
3. THE License_Dashboard SHALL support pagination for license tables with more than 100 entries
4. THE Backend_API SHALL cache frequently accessed data to reduce database queries
5. THE License_Dashboard SHALL use lazy loading for license details to improve initial load time
6. THE Backend_API SHALL use database indexes on License_Key and customer email fields

### Requirement 12: Security and Authentication

**User Story:** كمطور، أريد تأمين لوحة التحكم، حتى يتمكن فقط المستخدمون المصرح لهم من الوصول إليها.

#### Acceptance Criteria

1. THE License_Dashboard SHALL require authentication before displaying any license data
2. THE Backend_API SHALL validate the admin token for all API requests
3. THE admin token SHALL be stored securely in application configuration
4. WHEN authentication fails, THE License_Dashboard SHALL display a login prompt
5. THE License_Dashboard SHALL automatically logout after 30 minutes of inactivity
6. THE Backend_API SHALL use HTTPS for all communications in production mode
7. THE License_Dashboard SHALL not display sensitive data (passwords, tokens) in plain text

