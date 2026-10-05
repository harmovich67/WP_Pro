# Implementation Plan: Integrated License Dashboard

## Overview

This plan implements a comprehensive license management dashboard embedded within the Harmulizer Pro PyQt6 application. The implementation uses a hybrid architecture with a FastAPI backend running in a background thread and a web-based frontend displayed through QWebEngineView. All code will be written in Python for backend components, with HTML/CSS/JavaScript for the dashboard frontend.

## Tasks

- [x] 1. Set up API server thread infrastructure
  - Create `app/core/api_thread.py` with APIServerThread class extending QThread
  - Implement server lifecycle management (start, stop, health check)
  - Add pyqtSignal emissions for server_started and server_error events
  - Configure Uvicorn to run FastAPI in daemon thread mode
  - _Requirements: 1.6, 1.7, 7.1, 7.2_

- [ ]* 1.1 Write property test for API server lifecycle
  - **Property 1: API Server Lifecycle**
  - **Validates: Requirements 1.6, 1.7, 7.1**

- [x] 2. Integrate existing FastAPI backend
  - [x] 2.1 Move license_dashboard/main.py to app/core/license_api.py
    - Refactor to accept database path as parameter
    - Update database connection to use shared licenses.db
    - Ensure all existing endpoints remain functional
    - _Requirements: 7.2, 7.3, 7.4_

  - [x] 2.2 Add authentication middleware to FastAPI app
    - Implement Bearer token validation for admin endpoints
    - Exclude /api/verify and /api/deactivate from auth requirement
    - Return 401 for missing/invalid tokens
    - _Requirements: 7.8, 12.2, 12.3_

  - [ ]* 2.3 Write property test for authentication requirement
    - **Property 24: Authentication Requirement**
    - **Validates: Requirements 7.8, 12.2**

  - [x] 2.4 Update database models to match schema
    - Verify licenses and activations tables match design schema
    - Add missing indexes (key, email, tier, is_active)
    - Implement cascade deletion for activations
    - _Requirements: 2.9, 7.3_

  - [ ]* 2.5 Write property test for cascade deletion
    - **Property 7: Cascade Deletion**
    - **Validates: Requirements 2.9**

- [x] 3. Create theme bridge component
  - Create `app/ui/theme_bridge.py` with ThemeBridge class
  - Implement theme CSS variable generation from ThemeManager
  - Add CSS injection method for QWebEngineView
  - Connect to theme change signals from main application
  - _Requirements: 6.1, 6.2, 6.3, 6.5_

- [ ]* 3.1 Write property test for theme synchronization
  - **Property 19: Theme Synchronization**
  - **Validates: Requirements 6.1, 6.2, 6.3, 6.5**

- [x] 4. Create dashboard page widget
  - [x] 4.1 Create `app/ui/license_dashboard_page.py` with LicenseDashboardPage class
    - Extend QWidget and set up QWebEngineView
    - Initialize APIServerThread in constructor
    - Load dashboard HTML from embedded resources or local file
    - _Requirements: 1.2, 1.3, 1.5_

  - [ ]* 4.2 Write property test for dashboard page accessibility
    - **Property 2: Dashboard Page Accessibility**
    - **Validates: Requirements 1.2, 1.5**

  - [x] 4.3 Implement server lifecycle management in widget
    - Start API server when widget is shown
    - Handle server_started signal to load dashboard URL
    - Handle server_error signal to display error dialog
    - Implement graceful shutdown on widget close
    - _Requirements: 7.6, 7.7_

  - [ ]* 4.4 Write property test for graceful shutdown
    - **Property 22: Graceful Shutdown**
    - **Validates: Requirements 7.6**

  - [x] 4.5 Integrate ThemeBridge with dashboard widget
    - Initialize ThemeBridge with QWebEngineView and ThemeManager
    - Call sync_theme() after page load
    - Connect to theme change events
    - _Requirements: 6.1, 6.4, 6.5_

- [x] 5. Checkpoint - Verify backend integration
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement license CRUD operations
  - [x] 6.1 Implement license key generation function
    - Create generate_license_key(tier) function in app/core/license/license_manager.py
    - Use tier prefixes: HMF (free), HMB (basic), HMP (pro), HME (enterprise)
    - Generate 4 random hex segments of 4 characters each
    - Format as {PREFIX}-XXXX-XXXX-XXXX-XXXX
    - _Requirements: 2.3, 2.4_

  - [ ]* 6.2 Write property test for license key format
    - **Property 3: License Key Format**
    - **Validates: Requirements 2.4**

  - [ ]* 6.3 Write property test for license key uniqueness
    - **Property 4: License Key Uniqueness**
    - **Validates: Requirements 2.3, 10.7**

  - [x] 6.4 Implement POST /api/licenses endpoint
    - Accept LicenseCreateRequest with tier, email, customer_name, whatsapp, days_valid, max_activations, notes
    - Generate unique license key
    - Calculate expires_at from days_valid
    - Store in database with creation timestamp
    - Return complete LicenseResponse
    - _Requirements: 2.1, 2.2, 2.5_

  - [ ]* 6.5 Write property test for license creation persistence
    - **Property 5: License Creation Persistence**
    - **Validates: Requirements 2.5**

  - [x] 6.6 Implement GET /api/licenses endpoint
    - Support query parameters for filtering (tier, status, search)
    - Return list of LicenseResponse objects
    - Include current_activations count for each license
    - _Requirements: 4.6, 5.2, 5.5_

  - [x] 6.7 Implement PUT /api/licenses/{id} endpoint
    - Accept LicenseUpdateRequest with optional fields
    - Update only provided fields
    - Update last_modified timestamp
    - Return updated LicenseResponse
    - _Requirements: 2.6, 2.7_

  - [ ]* 6.8 Write property test for license update timestamp
    - **Property 6: License Update Timestamp**
    - **Validates: Requirements 2.7**

  - [x] 6.9 Implement DELETE /api/licenses/{id} endpoint
    - Verify license exists
    - Delete license record (cascade will remove activations)
    - Return success response
    - _Requirements: 2.8, 2.9_

- [x] 7. Implement activation management
  - [x] 7.1 Implement GET /api/licenses/{id}/activations endpoint
    - Query all activations for given license_id
    - Return list with machine_id, activated_at, last_seen, is_active
    - _Requirements: 3.1, 3.2, 3.3_

  - [ ]* 7.2 Write property test for activation display completeness
    - **Property 9: Activation Display Completeness**
    - **Validates: Requirements 3.1, 3.2, 3.3**

  - [x] 7.3 Implement DELETE /api/activations/{id} endpoint
    - Mark activation as inactive (is_active = False)
    - Update activation record in database
    - _Requirements: 3.4, 3.5_

  - [ ]* 7.4 Write property test for activation count decrement
    - **Property 10: Activation Count Decrement**
    - **Validates: Requirements 3.4, 3.5**

  - [x] 7.5 Add activation limit warning logic
    - Calculate warning threshold (80% of max_activations)
    - Add warning flag to LicenseResponse when threshold exceeded
    - _Requirements: 3.6_

  - [ ]* 7.6 Write property test for activation limit warning
    - **Property 11: Activation Limit Warning**
    - **Validates: Requirements 3.6**

- [x] 8. Implement statistics and reporting
  - [x] 8.1 Create DashboardStats model and calculation method
    - Implement DashboardStats.calculate(db) class method
    - Query total, active, expired license counts
    - Calculate counts by tier (free, basic, pro, enterprise)
    - Count total active activations
    - Calculate monthly and annual revenue
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.8_

  - [ ]* 8.2 Write property test for statistics completeness
    - **Property 12: Statistics Completeness**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

  - [ ]* 8.3 Write property test for revenue calculation
    - **Property 15: Revenue Calculation**
    - **Validates: Requirements 4.8**

  - [x] 8.4 Implement GET /api/stats endpoint
    - Call DashboardStats.calculate(db)
    - Return statistics as JSON
    - Cache result for 5 seconds to improve performance
    - _Requirements: 4.5, 11.1, 11.4_

  - [ ]* 8.5 Write property test for statistics real-time update
    - **Property 13: Statistics Real-Time Update**
    - **Validates: Requirements 4.5, 11.2**

- [x] 9. Checkpoint - Verify API endpoints
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Update dashboard frontend HTML/CSS/JS
  - [x] 10.1 Update license_dashboard/index.html with API integration
    - Update DashboardAPI class to use correct endpoint URLs
    - Add authentication token to all API requests
    - Implement error handling for API failures
    - _Requirements: 7.5, 10.5_

  - [ ]* 10.2 Write property test for API connection error handling
    - **Property 31: API Connection Error Handling**
    - **Validates: Requirements 10.5**

  - [x] 10.3 Implement statistics cards display
    - Create cards for total, active, expired, and by-tier counts
    - Add revenue display (monthly and annual)
    - Implement auto-refresh every 30 seconds
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.8_

  - [x] 10.4 Implement license table with sorting
    - Display all license fields in table
    - Add sortable column headers (creation date, expiration, tier, status)
    - Show current activations vs max activations
    - Add action buttons (edit, delete, view activations)
    - _Requirements: 4.6, 4.7_

  - [ ]* 10.5 Write property test for license table display
    - **Property 14: License Table Display**
    - **Validates: Requirements 4.6, 4.7**

  - [x] 10.6 Implement search and filter functionality
    - Add search input for license key, customer name, email
    - Add tier filter dropdown (all, free, basic, pro, enterprise)
    - Add status filter dropdown (all, active, inactive, expired)
    - Display filtered result count
    - Add "Clear Filters" button
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [ ]* 10.7 Write property test for search filtering
    - **Property 16: Search Filtering**
    - **Validates: Requirements 5.2**

  - [ ]* 10.8 Write property test for filter application
    - **Property 17: Filter Application**
    - **Validates: Requirements 5.5, 5.6**

  - [ ]* 10.9 Write property test for filter reset
    - **Property 18: Filter Reset**
    - **Validates: Requirements 5.7**

  - [x] 10.10 Implement create/edit license modals
    - Create modal form with all license fields
    - Add client-side validation for email, WhatsApp, numbers
    - Display validation errors inline
    - Submit to POST or PUT endpoint
    - Refresh table on success
    - _Requirements: 2.1, 2.2, 2.6, 10.1, 10.2, 10.3, 10.4_

  - [ ]* 10.11 Write property test for input validation
    - **Property 30: Input Validation**
    - **Validates: Requirements 10.1, 10.2, 10.3, 10.4**

  - [x] 10.12 Implement delete confirmation dialog
    - Show confirmation modal with license details
    - Require explicit confirmation before deletion
    - Display success/error message after deletion
    - _Requirements: 2.8_

  - [ ]* 10.13 Write property test for deletion confirmation
    - **Property 8: Deletion Confirmation**
    - **Validates: Requirements 2.8**

- [x] 11. Implement WhatsApp integration
  - [x] 11.1 Add WhatsApp button to license table rows
    - Show button only if license has WhatsApp number
    - Style button with WhatsApp green color
    - _Requirements: 9.1, 9.4_

  - [ ]* 11.2 Write property test for WhatsApp button visibility
    - **Property 27: WhatsApp Button Visibility**
    - **Validates: Requirements 9.1, 9.4**

  - [x] 11.3 Implement WhatsApp message generation
    - Create pre-filled message with license key and welcome text
    - Format message in Arabic/English based on customer preference
    - Open WhatsApp Web URL with encoded message
    - _Requirements: 9.2, 9.3_

  - [ ]* 11.4 Write property test for WhatsApp message content
    - **Property 28: WhatsApp Message Content**
    - **Validates: Requirements 9.2, 9.3**

  - [x] 11.5 Add WhatsApp number validation
    - Validate international format (starts with +)
    - Display error if format is invalid
    - _Requirements: 9.5_

  - [ ]* 11.6 Write property test for WhatsApp number validation
    - **Property 29: WhatsApp Number Validation**
    - **Validates: Requirements 9.5**

- [x] 12. Implement responsive design
  - [x] 12.1 Add responsive CSS media queries
    - Stack statistics cards vertically on screens < 1024px
    - Enable horizontal scrolling for table on narrow screens
    - Hide non-essential columns (notes, last_modified) on screens < 800px
    - Scale font sizes proportionally
    - _Requirements: 8.1, 8.2, 8.3, 8.5, 8.6_

  - [ ]* 12.2 Write property test for responsive layout adaptation
    - **Property 25: Responsive Layout Adaptation**
    - **Validates: Requirements 8.1, 8.2, 8.3**

  - [ ]* 12.3 Write property test for responsive column hiding
    - **Property 26: Responsive Column Hiding**
    - **Validates: Requirements 8.6**

  - [x] 12.4 Test dashboard at minimum window size (800x600)
    - Verify all functionality remains accessible
    - Ensure readability is maintained
    - _Requirements: 8.4_

- [x] 13. Implement theme synchronization
  - [x] 13.1 Define CSS variables for theme colors
    - Create :root CSS variables for all theme colors
    - Map PyQt6 theme colors to CSS variables
    - Support both dark and light themes
    - _Requirements: 6.4, 6.6, 6.7_

  - [x] 13.2 Implement JavaScript theme detection
    - Add JavaScript function to receive theme updates from PyQt6
    - Update CSS variables when theme changes
    - Apply theme immediately without page reload
    - _Requirements: 6.5_

  - [x] 13.3 Test theme switching
    - Verify dark theme applies correctly
    - Verify light theme applies correctly
    - Verify theme changes propagate within 100ms
    - _Requirements: 6.1, 6.2, 6.3, 6.5_

- [x] 14. Implement error handling and validation
  - [x] 14.1 Add backend validation for all endpoints
    - Validate email format using regex
    - Validate positive integers for days_valid and max_activations
    - Validate tier is one of allowed values
    - Return 422 with field-specific errors
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 14.2 Add database error handling
    - Wrap all database operations in try-except blocks
    - Log errors with full stack trace
    - Return user-friendly error messages
    - Implement transaction rollback on errors
    - _Requirements: 10.6_

  - [ ]* 14.3 Write property test for database error handling
    - **Property 32: Database Error Handling**
    - **Validates: Requirements 10.6**

  - [x] 14.3 Add API error handling in frontend
    - Display connection errors in banner at top of page
    - Show specific error messages from API responses
    - Implement retry mechanism for failed requests
    - _Requirements: 10.5, 7.7_

  - [ ]* 14.4 Write property test for API failure handling
    - **Property 23: API Failure Handling**
    - **Validates: Requirements 7.7**

- [x] 15. Implement authentication and security
  - [x] 15.1 Add login page to dashboard
    - Create simple login form with password field
    - Validate admin token on submit
    - Store token in sessionStorage (not localStorage for security)
    - Redirect to dashboard on success
    - _Requirements: 12.1, 12.4_

  - [ ]* 15.2 Write property test for authentication gate
    - **Property 35: Authentication Gate**
    - **Validates: Requirements 12.1, 12.4**

  - [x] 15.3 Implement inactivity timeout
    - Track last user interaction timestamp
    - Check for inactivity every minute
    - Logout after 30 minutes of inactivity
    - Clear session and redirect to login
    - _Requirements: 12.5_

  - [ ]* 15.4 Write property test for inactivity timeout
    - **Property 36: Inactivity Timeout**
    - **Validates: Requirements 12.5**

  - [x] 15.5 Implement sensitive data protection
    - Mask admin tokens in UI (show only last 4 characters)
    - Never log sensitive data
    - Use HTTPS in production (configuration option)
    - _Requirements: 12.6, 12.7_

  - [ ]* 15.6 Write property test for sensitive data protection
    - **Property 37: Sensitive Data Protection**
    - **Validates: Requirements 12.7**

- [x] 16. Checkpoint - Verify frontend integration
  - Ensure all tests pass, ask the user if questions arise.

- [x] 17. Add dashboard to main window
  - [x] 17.1 Update app/ui/main_window.py to include dashboard page
    - Import LicenseDashboardPage
    - Add "License Dashboard" item to sidebar navigation
    - Create dashboard page instance with license_manager and theme_manager
    - Add page to stacked widget
    - Connect sidebar click to show dashboard page
    - _Requirements: 1.1, 1.2_

  - [x] 17.2 Update sidebar styling for dashboard item
    - Add icon for dashboard (use existing icon set)
    - Match styling with other sidebar items
    - Highlight when selected
    - _Requirements: 1.4_

- [x] 18. Implement performance optimizations
  - [x] 18.1 Add database indexes
    - Create indexes on licenses(key, email, tier, is_active)
    - Create indexes on activations(license_id, machine_id, is_active)
    - _Requirements: 11.6_

  - [x] 18.2 Implement statistics caching
    - Cache statistics results for 5 seconds
    - Invalidate cache on license data changes
    - _Requirements: 11.1, 11.4_

  - [x] 18.3 Implement pagination for license table
    - Add pagination controls (page size: 50)
    - Update API endpoint to support limit and offset parameters
    - Show page numbers and navigation buttons
    - _Requirements: 11.3_

  - [ ]* 18.4 Write property test for pagination support
    - **Property 34: Pagination Support**
    - **Validates: Requirements 11.3**

  - [x] 18.5 Optimize initial dashboard load
    - Load statistics first, then license table
    - Use lazy loading for license details
    - Minimize initial API requests
    - _Requirements: 11.1, 11.5_

  - [ ]* 18.6 Write property test for initial load performance
    - **Property 33: Initial Load Performance**
    - **Validates: Requirements 11.1**

- [x] 19. Add comprehensive error logging
  - [x] 19.1 Set up logging configuration
    - Create log file at ~/.config/HarmulizerPro/logs/dashboard.log
    - Configure log rotation (max 10MB, keep 5 files)
    - Set log levels (ERROR, WARNING, INFO, DEBUG)
    - _Requirements: 10.6_

  - [x] 19.2 Add logging to all critical operations
    - Log API server start/stop
    - Log all license CRUD operations
    - Log authentication attempts
    - Log database errors with stack traces
    - _Requirements: 10.6_

- [x] 20. Final integration and testing
  - [x] 20.1 Test complete license lifecycle
    - Create license through dashboard
    - Verify license in database
    - Update license details
    - View activations
    - Delete license
    - Verify cascade deletion
    - _Requirements: All_

  - [x] 20.2 Test theme synchronization end-to-end
    - Start application in dark mode
    - Open dashboard and verify dark theme
    - Switch to light mode in main app
    - Verify dashboard updates to light theme
    - _Requirements: 6.1, 6.2, 6.3, 6.5_

  - [x] 20.3 Test error scenarios
    - Test with database locked
    - Test with API server port in use
    - Test with invalid authentication
    - Test with network errors
    - Verify appropriate error messages displayed
    - _Requirements: 10.5, 10.6, 7.7_

  - [x] 20.4 Test responsive design at different window sizes
    - Test at 1920x1080 (full desktop)
    - Test at 1024x768 (small desktop)
    - Test at 800x600 (minimum size)
    - Verify all functionality accessible at all sizes
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [x] 21. Final checkpoint - Complete system verification
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional testing tasks and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties from the design document
- Unit tests should be written alongside implementation for immediate feedback
- The implementation follows a bottom-up approach: backend first, then frontend, then integration
- All Python code should follow PEP 8 style guidelines
- All JavaScript code should follow modern ES6+ standards
- Database operations should use SQLAlchemy ORM for consistency with existing codebase
- API endpoints should follow RESTful conventions
- Frontend should be accessible and follow WCAG guidelines where applicable
