# FiscGuy API Endpoints - Fiscalization Service Setup Guide

This document provides a comprehensive guide for setting up FiscGuy as a fiscalization service that integrates with your main ERP system for teams migrating from an existing ZIMRA fiscal system.

## Architecture Overview

### Fiscalization Service Pattern
FiscGuy runs as a standalone Django service that:
- **Handles all ZIMRA fiscal operations** (receipts, credit notes, fiscal days)
- **Provides REST API endpoints** for your main ERP to consume
- **Manages fiscal compliance** independently of your business logic
- **Acts as a microservice** in your overall system architecture

```
Main ERP System          Fiscalization Service (FiscGuy)     ZIMRA FDMS
       │                           │                           │
       ├───> Submit Receipt ───────>│                           │
       │                           ├───> Format & Sign ───────>│
       │                           │                           │
       ├───> Get Status ───────────>│<───> Response ────────────│
       │                           │                           │
       └───> Close Day ────────────>│                           │
                                   │
```

## Service Setup Steps

### Step 1: Create Django Application

1. **Install FiscGuy Library**
   ```bash
   pip install fiscguy
   ```

2. **Create New Django Project**
   ```bash
   django-admin startproject fiscalization_service
   cd fiscalization_service
   ```

3. **Configure Django Settings**
   ```python
   # settings.py
   INSTALLED_APPS = [
       'django.contrib.admin',
       'django.contrib.auth',
       'django.contrib.contenttypes',
       'django.contrib.sessions',
       'django.contrib.messages',
       'django.contrib.staticfiles',
       
       'rest_framework',
       'fiscguy',  # Add fiscguy here
   ]
   
   # Database configuration
   DATABASES = {
       'default': {
           'ENGINE': 'django.db.backends.postgresql',
           'NAME': 'fiscalization_service',
           'USER': 'your_db_user',
           'PASSWORD': 'your_db_password',
           'HOST': 'localhost',
           'PORT': '5432',
       }
   }
   ```

4. **Make and Apply Migrations**
   ```bash
   python manage.py makemigrations fiscguy
   python manage.py migrate fiscguy
   python manage.py migrate
   ```

5. **Configure URLs**
   ```python
   # urls.py
   from django.contrib import admin
   from django.urls import path, include

   urlpatterns = [
       path('admin/', admin.site.urls),
       path('api/fiscguy/', include('fiscguy.urls')),
   ]
   ```

6. **Create Superuser for Admin Access**
   ```bash
   python manage.py createsuperuser
   ```

### Step 2: Service Configuration

1. **Start the Service**
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```

2. **Access Django Admin**
   - Navigate to `http://localhost:8000/admin/`
   - Login with superuser credentials

3. **Configure Service for Production**
   ```bash
   # Production deployment with gunicorn
   pip install gunicorn
   gunicorn fiscalization_service.wsgi:application --bind 0.0.0.0:8000
   ```

## ERP Integration Guide

### Receipt Format Mapping

Your main ERP system needs to map its receipt data to the FiscGuy API format. Below are the exact field mappings:

#### Standard Receipt Mapping
```json
// Your ERP Receipt Format → FiscGuy API Format
{
  "receipt_type": "fiscalinvoice",  // Fixed value
  "currency": "USD",               // From your ERP: currency_code
  "total_amount": "100.00",        // From your ERP: total_amount
  "payment_terms": "cash",         // From your ERP: payment_method (cash/credit/other)
  "buyer": {                       // From your ERP: customer_info
    "name": "Customer Name",       // customer_name
    "address": "Customer Address", // customer_address
    "phonenumber": "+263123456789", // customer_phone
    "tin_number": "123456789",     // customer_tin (optional)
    "email": "customer@example.com" // customer_email (optional)
  },
  "lines": [                       // From your ERP: line_items
    {
      "product": "Product Name",   // product_name
      "quantity": 1,               // quantity
      "unit_price": "100.00",      // unit_price
      "line_total": "100.00",      // line_total (quantity × unit_price)
      "tax_name": "standard rated 15.5%" // tax_name (from tax mapping)
    }
  ]
}
```

#### Credit Note Mapping
```json
// Your ERP Credit Note Format → FiscGuy API Format
{
  "receipt_type": "creditnote",           // Fixed value
  "credit_note_reference": "R-00001",     // From your ERP: original_receipt_id
  "credit_note_reason": "discount",       // From your ERP: reason_code
  "currency": "USD",                      // From your ERP: currency_code
  "total_amount": "-100.00",              // From your ERP: total_amount (negative)
  "payment_terms": "cash",                // From your ERP: payment_method
  "lines": [                              // From your ERP: line_items
    {
      "product": "Product Name",          // product_name
      "quantity": 1,                      // quantity
      "unit_price": "-100.00",            // unit_price (negative)
      "line_total": "-100.00",            // line_total (negative)
      "tax_name": "standard rated 15.5%"  // tax_name (from tax mapping)
    }
  ]
}
```

### Tax Mapping Configuration

Map your ERP product categories to FiscGuy tax types:

#### Step 1: Load Available Taxes
```bash
curl -X GET http://localhost:8000/api/fiscguy/taxes/
```

#### Step 2: Create Tax Mapping in Your ERP
```python
# Example tax mapping in your ERP system
ERP_TAX_MAPPING = {
    # Your ERP Tax Code → FiscGuy Tax Name
    "STD_VAT": "standard rated 15.5%",
    "ZERO_VAT": "zero rated",
    "EXEMPT": "exempt",
    "WITHHOLDING": "withholding tax",
    "IMPORT_VAT": "import vat",
}

def get_fiscguy_tax_name(erp_tax_code):
    """Map ERP tax code to FiscGuy tax name"""
    return ERP_TAX_MAPPING.get(erp_tax_code, "standard rated 15.5%")
```

#### Step 3: Product Tax Configuration
```python
# Configure each product in your ERP with appropriate tax
PRODUCT_TAX_CONFIG = {
    "product_001": "STD_VAT",      # Standard rated products
    "product_002": "ZERO_VAT",     # Zero-rated products
    "product_003": "EXEMPT",       # Exempt products
    "service_001": "STD_VAT",      # Standard rated services
}

def get_tax_for_product(product_code):
    """Get tax code for a product"""
    erp_tax_code = PRODUCT_TAX_CONFIG.get(product_code, "STD_VAT")
    return get_fiscguy_tax_name(erp_tax_code)
```

### ERP Integration Examples

#### Python Integration Example
```python
import requests
from decimal import Decimal

class FiscalizationClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.api_base = f"{base_url}/api/fiscguy"
    
    def submit_receipt(self, erp_receipt_data):
        """Convert ERP receipt to FiscGuy format and submit"""
        fiscguy_data = self._map_receipt_format(erp_receipt_data)
        
        response = requests.post(
            f"{self.api_base}/receipts/",
            json=fiscguy_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 201:
            return response.json()
        else:
            raise Exception(f"Fiscalization failed: {response.text}")
    
    def _map_receipt_format(self, erp_data):
        """Map ERP receipt format to FiscGuy format"""
        return {
            "receipt_type": erp_data.get("type", "fiscalinvoice"),
            "currency": erp_data["currency"],
            "total_amount": str(erp_data["total_amount"]),
            "payment_terms": erp_data["payment_method"],
            "buyer": {
                "name": erp_data["customer"]["name"],
                "address": erp_data["customer"]["address"],
                "phonenumber": erp_data["customer"]["phone"],
                "tin_number": erp_data["customer"].get("tin", ""),
                "email": erp_data["customer"].get("email", ""),
            },
            "lines": [
                {
                    "product": line["product_name"],
                    "quantity": line["quantity"],
                    "unit_price": str(line["unit_price"]),
                    "line_total": str(line["line_total"]),
                    "tax_name": self._get_tax_name(line["product_code"]),
                }
                for line in erp_data["line_items"]
            ]
        }
    
    def _get_tax_name(self, product_code):
        """Get FiscGuy tax name for product"""
        return get_tax_for_product(product_code)
    
    def get_status(self):
        """Get fiscal device status"""
        response = requests.get(f"{self.api_base}/get-status/")
        return response.json()
    
    def open_day(self):
        """Open fiscal day"""
        response = requests.get(f"{self.api_base}/open-day/")
        return response.json()
    
    def close_day(self):
        """Close fiscal day"""
        response = requests.get(f"{self.api_base}/close-day/")
        return response.json()

# Usage in your ERP
fiscal_client = FiscalizationClient()

# Submit receipt from your ERP system
erp_receipt = {
    "type": "fiscalinvoice",
    "currency": "USD",
    "total_amount": 150.00,
    "payment_method": "cash",
    "customer": {
        "name": "John Doe",
        "address": "123 Main St",
        "phone": "+263123456789",
        "tin": "123456789",
        "email": "john@example.com"
    },
    "line_items": [
        {
            "product_code": "product_001",
            "product_name": "Widget A",
            "quantity": 2,
            "unit_price": 75.00,
            "line_total": 150.00
        }
    ]
}

try:
    fiscal_receipt = fiscal_client.submit_receipt(erp_receipt)
    logger.info(f"Receipt submitted successfully: {fiscal_receipt['id']}")
except Exception as e:
    logger.error(f"Fiscalization error: {e}")
```

#### Integration Workflow
1. **Customer makes purchase in ERP**
2. **ERP generates receipt data**
3. **ERP maps data to FiscGuy format**
4. **ERP calls FiscGuy API to submit receipt**
5. **FiscGuy handles ZIMRA communication**
6. **ERP stores fiscal receipt ID for reference**

### Error Handling and Retry Logic

```python
import time
from requests.exceptions import RequestException

class FiscalizationClient:
    def submit_receipt_with_retry(self, erp_receipt_data, max_retries=3):
        """Submit receipt with retry logic"""
        for attempt in range(max_retries):
            try:
                return self.submit_receipt(erp_receipt_data)
            except RequestException as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff 
            except Exception as e:
                raise
```

### Device Initialization Options

You have two approaches for device setup:

#### Option 1: Skip Device Initialization (Confident Teams)
If you're confident in your setup and ready for production:

1. **Skip `init_device` command entirely**
2. **Manually configure via Django Admin** (see Migration Setup Steps)
3. **Use your production certificates from the start**
4. **Configure production device ID and taxes immediately**

**Best for**: Teams with existing ZIMRA experience and ready production certificates

#### Option 2: Test-First Approach (Recommended)
Test your integration with ZIMRA test environment first:

1. **Run device initialization with test environment**:
   ```bash
   python manage.py init_device
   ```
   - Choose "no" for test environment when prompted
   - Use ZIMRA test credentials and certificates
   - Test device will be created with test certificates

2. **Test your integration thoroughly**:
   - Submit test receipts
   - Verify fiscal day operations
   - Test all API endpoints
   - Validate tax mappings

3. **Migrate to production**:
   - Replace test certificates with production certificates
   - Update device ID for production
   - Map taxes for production environment
   - Switch environment to production

**Best for**: Teams new to FiscGuy or wanting to validate integration before production

### Test-to-Production Migration Workflow

#### Step 1: Initial Test Setup
Run `python manage.py init_device` and choose test environment when prompted. Follow the setup wizard to configure your test device.

#### Step 2: Test Integration
Test your ERP integration by submitting receipts through the API endpoints to verify everything works correctly in the test environment.

#### Step 3: Production Migration
After successful testing, migrate to production:

##### 3.1 Replace Certificates via Django Admin
- Access Django Admin → `Certs` model
- Edit existing test certificate record
- Replace `cert_file` with your production certificate
- Replace `key_file` with your production private key
- Keep the same device link

##### 3.2 Update Device for Production
- Access Django Admin → `Device` model
- Edit your test device record
- Update `device_id` to your production device ID
- Update `branch_id` to your production branch ID
- Change `environment` from "test" to "production"

##### 3.3 Update Production Configuration
- Access Django Admin → `Configuration` model
- Update with your production company details:
  - Company name, TIN, VAT numbers
  - Physical and postal addresses
  - Phone number and email
  - Production device and branch IDs

##### 3.4 Map Production Taxes
- Access Django Admin → `Taxes` model
- Update tax records to match production requirements:
  - Standard VAT (15.5%)
  - Zero-rated (0%)
  - Exempt (0%)
  - Any other tax types as required

#### Step 4: Verify Production Setup
Test your production setup by:
- Checking device connectivity with ping endpoint
- Verifying configuration details
- Submitting test receipts to production environment

### Skip Device Initialization
- **No need** to run `python manage.py init_device`
- **Copy existing production certificates** to the Certs model via Django admin
- **Import existing device configuration** through Django admin or direct database operations

### Previous Day Setup (One-time)
- **Create a single previous day record** to enable proper day accumulation
- **Required for seamless continuation** of fiscal day numbering
- **Configure once** during initial migration

## Base URL

All endpoints are prefixed with `/api/fiscguy/` when included in your Django project:

```python
# urls.py
urlpatterns = [
    path('api/fiscguy/', include('fiscguy.urls')),
]
```

**Example Endpoint URLs:**
- `GET /api/fiscguy/open-day/`
- `POST /api/fiscguy/receipts/`
- `GET /api/fiscguy/get-status/`
- `GET /api/fiscguy/taxes/`

## Migration Setup Steps

### Step 1: Certificate Migration
Instead of running `init_device`, manually migrate your existing certificates:

1. **Access Django Admin** → `Certs` model
2. **Create new Cert record** with your existing production certificates:
   - `cert_file`: Upload your existing production certificate
   - `key_file`: Upload your existing private key
   - `device`: Link to your device record (create via admin if needed)

### Step 2: Device Configuration
Import your existing device configuration:

1. **Access Django Admin** → `Device` model
2. **Create device record** with existing device details:
   - `device_id`: Your existing device ID
   - `branch_id`: Your existing branch ID
   - `environment`: Set to `production`
   - Link to the certificate created in Step 1

3. **Access Django Admin** → `Configuration` model
4. **Import existing configuration**:
   - `tax_payer_name`: Company name from existing system
   - `tin_number`: Existing TIN
   - `vat_number`: Existing VAT number
   - `device`: Link to device from Step 2

### Step 3: Previous Day Setup (One-time)
Create a single previous day record for day continuity:

1. **Access Django Admin** → `FiscalDay` model
2. **Create previous day record**:
   - `day_no`: Your last fiscal day number from existing system
   - `is_open`: `False` (closed day)
   - `device`: Link to your device
   - `date`: The date of your last fiscal day
   - **Do NOT create FiscalCounter records** for this day

### Step 4: Tax Migration
Copy your existing tax configuration through Django admin:

1. **Access Django Admin** → `Taxes` model
2. **Create tax records** matching your existing system:
   - `tax_id`: Use existing tax IDs from ZIMRA (must match exactly)
   - `name`: Tax names exactly as in ZIMRA (must match exactly)
   - `percent`: Correct tax percentages
   - `code`: Tax codes matching your existing setup

**Important**: Tax names and IDs must match ZIMRA's requirements exactly for receipt submission to work properly.

## Authentication

Currently, the API does not require authentication. Ensure you secure these endpoints appropriately in production.

## Endpoints Overview

### Fiscal Day Management

#### Open Fiscal Day
- **Endpoint**: `GET /api/fiscguy/open-day/`
- **Description**: Opens a new fiscal day for fiscal operations
- **Response**: 
  ```json
  {
    "message": "Fiscal day opened successfully",
    "day_no": 123,
    "status": "open"
  }
  ```
- **Notes**: If a fiscal day is already open, returns early with existing day info

#### Close Fiscal Day
- **Endpoint**: `GET /api/fiscguy/close-day/`
- **Description**: Closes the currently open fiscal day
- **Response**: Final device/fiscal status from ZIMRA FDMS
- **Process**: 
  - Collects fiscal counters
  - Builds and signs closing string
  - Submits to ZIMRA
  - Updates fiscal day status
- **Error**: Returns `{"error": "No open fiscal day to close"}` if no day is open

### Receipt Management

#### List Receipts
- **Endpoint**: `GET /api/fiscguy/receipts/`
- **Description**: Lists all receipts ordered by creation date
- **Response**: Array of receipt objects with full details including lines and buyer info

#### Create/Submit Receipt
- **Endpoint**: `POST /api/fiscguy/receipts/`
- **Description**: Creates and submits a new receipt to ZIMRA
- **Request Body**:
  ```json
  {
    "receipt_type": "fiscalinvoice",
    "currency": "USD",
    "total_amount": "100.00",
    "payment_terms": "cash",
    "buyer": {
      "name": "Customer Name",
      "address": "Customer Address",
      "phonenumber": "+263123456789",
      "tin_number": "123456789",
      "email": "customer@example.com"
    },
    "lines": [
      {
        "product": "Product Name",
        "quantity": 1,
        "unit_price": "100.00",
        "line_total": "100.00",
        "tax_name": "standard rated 15.5%"
      }
    ]
  }
  ```
- **Receipt Types**: `fiscalinvoice`, `creditnote`
- **Payment Terms**: `cash`, `credit`, `other`
- **Response**: Created receipt object with ID and all details
- **Status**: 201 on success, 400 on error

#### Create Credit Note
- **Endpoint**: `POST /api/fiscguy/receipts/`
- **Description**: Creates a credit note for an existing receipt
- **Request Body**:
  ```json
  {
    "receipt_type": "creditnote",
    "credit_note_reference": "R-00001",
    "credit_note_reason": "discount",
    "currency": "USD",
    "total_amount": "-100.00",
    "payment_terms": "cash",
    "lines": [
      {
        "product": "Product Name",
        "quantity": 1,
        "unit_price": "-100.00",
        "line_total": "-100.00",
        "tax_name": "standard rated 15.5%"
      }
    ]
  }
  ```
- **Notes**: 
  - `credit_note_reference` must exist in both FiscGuy and ZIMRA
  - Amounts should be negative
  - `credit_note_reason` can be: `discount`, `return`, `cancellation`, `other`

#### Get Receipt Details
- **Endpoint**: `GET /api/fiscguy/receipts/{id}/`
- **Description**: Retrieves detailed information for a specific receipt
- **Parameters**: `id` - Receipt ID
- **Response**: Complete receipt object with lines and buyer information

### Device Status and Configuration

#### Get Device Status
- **Endpoint**: `GET /api/fiscguy/get-status/`
- **Description**: Fetches current device and fiscal day status from ZIMRA FDMS
- **Response**: Status payload from ZIMRA including device info and fiscal day state

#### Get Device Configuration
- **Endpoint**: `GET /api/fiscguy/configuration/`
- **Description**: Retrieves stored device configuration
- **Response**:
  ```json
  {
    "tax_payer_name": "Company Name",
    "tin_number": "123456789",
    "vat_number": "VAT123456",
    "physical_address": "123 Main St",
    "postal_address": "P.O. Box 123",
    "phone_number": "+263123456789",
    "email": "company@example.com",
    "device_id": "DEVICE123",
    "branch_id": "BRANCH001"
  }
  ```
- **Notes**: Returns empty object `{}` if no configuration exists

#### Ping Device
- **Endpoint**: `GET /api/fiscguy/get-ping/`
- **Description**: Pings the ZIMRA device to check connectivity
- **Response**:
  ```json
  {
    "deviceID": "DEVICE123",
    "reportingFrequency": 3600
  }
  ```

### Tax Information

#### Get Available Taxes
- **Endpoint**: `GET /api/fiscguy/taxes/`
- **Description**: Lists all available tax types configured in the system
- **Response**:
  ```json
  [
    {
      "id": 1,
      "code": "STD",
      "name": "standard rated 15.5%",
      "tax_id": 1,
      "percent": 15.5
    },
    {
      "id": 2,
      "code": "ZERO",
      "name": "zero rated",
      "tax_id": 2,
      "percent": 0.0
    }
  ]
  ```

### Buyer Management

#### Buyer CRUD Operations
- **Base Path**: `/api/fiscguy/buyer/`
- **Description**: Full CRUD operations for buyer/customer management
- **Endpoints**:
  - `GET /api/fiscguy/buyer/` - List all buyers
  - `POST /api/fiscguy/buyer/` - Create new buyer
  - `GET /api/fiscguy/buyer/{id}/` - Get specific buyer
  - `PUT /api/fiscguy/buyer/{id}/` - Update buyer
  - `DELETE /api/fiscguy/buyer/{id}/` - Delete buyer
- **Request/Response**: Standard Django REST Framework ModelViewSet behavior

## Important Notes

### Migration-Specific Behavior

#### Automatic Fiscal Day Opening
When submitting the first receipt without an open fiscal day, FiscGuy will **automatically open a new fiscal day**. This includes:
- Silent fiscal day opening
- 5-second delay for ZIMRA processing
- Subsequent receipts use the same open fiscal day
- **Day numbering continues from your previous day record** (Step 3 setup)

#### Certificate Management
- **No automatic certificate generation** during migration
- **Use existing production certificates** from your current system
- **Certificates are managed via Django Admin** → `Certs` model
- **Ensure certificates are valid and not expired**

#### Day Continuity
- **Previous day record ensures proper day numbering** (e.g., if last day was 100, next will be 101)
- **Only create ONE previous day record** during initial migration
- **Do not migrate historical receipt data** - start fresh from the new fiscal day

### Error Handling
All endpoints return consistent error responses:
```json
{
  "error": "Error description"
}
```
Common HTTP status codes:
- `200` - Success
- `201` - Created (for POST requests)
- `400` - Bad Request (validation errors, business logic errors)
- `404` - Not Found (for specific resource requests)

### Prerequisites for Migration
1. **Existing ZIMRA System**: You must have an active ZIMRA fiscal system with valid certificates
2. **Database Access**: Access to Django admin for manual data entry
3. **Certificate Files**: Your current production certificate and private key files
4. **Last Fiscal Day Number**: Know your last fiscal day number from the existing system
5. **Device Information**: Current device ID, branch ID, and configuration details

### Response Format
All successful responses follow REST conventions:
- GET requests return the requested data
- POST requests return the created resource
- PUT/PATCH requests return the updated resource
- DELETE requests return 204 No Content or the deleted resource

## Migration Example Usage

### Complete Migration Flow
```bash
# 1. Verify migration setup (after completing Steps 1-4 above)
curl -X GET http://localhost:8000/api/fiscguy/get-ping/
curl -X GET http://localhost:8000/api/fiscguy/get-status/
curl -X GET http://localhost:8000/api/fiscguy/configuration/

# 2. Open first fiscal day in new system (continues from previous day)
curl -X GET http://localhost:8000/api/fiscguy/open-day/

# 3. Submit first receipt in new system
curl -X POST http://localhost:8000/api/fiscguy/receipts/ \
  -H "Content-Type: application/json" \
  -d '{
    "receipt_type": "fiscalinvoice",
    "currency": "USD",
    "total_amount": "100.00",
    "payment_terms": "cash",
    "lines": [
      {
        "product": "Test Item",
        "quantity": 1,
        "unit_price": "100.00",
        "line_total": "100.00",
        "tax_name": "standard rated 15.5%"
      }
    ]
  }'

# 4. Check status
curl -X GET http://localhost:8000/api/fiscguy/get-status/

# 5. Close fiscal day when done
curl -X GET http://localhost:8000/api/fiscguy/close-day/
```

### Migration Verification Checklist
After completing the migration setup, verify:

- [ ] **Device Ping**: `GET /api/fiscguy/get-ping/` returns device info
- [ ] **Configuration**: `GET /api/fiscguy/configuration/` shows your company details
- [ ] **Taxes**: `GET /api/fiscguy/taxes/` lists your tax types
- [ ] **Status**: `GET /api/fiscguy/get-status/` shows device status
- [ ] **Day Opening**: `GET /api/fiscguy/open-day/` opens next fiscal day (previous_day_no + 1)
- [ ] **Receipt Submission**: `POST /api/fiscguy/receipts/` creates receipts successfully

### Post-Migration Operations

### Programmatic Usage
For programmatic access, you can also use the Python API directly:

```python
from fiscguy import open_day, close_day, submit_receipt, get_status

# Open fiscal day
open_day()

# Submit receipt
receipt = submit_receipt(receipt_data)

# Get status
status = get_status()

# Close fiscal day
close_day()
```

## Testing Migration

### Pre-Migration Testing
Before switching from your existing system:

1. **Test Certificate Validity**: Ensure your certificates work with ZIMRA test environment
2. **Verify Tax Configuration**: Confirm tax IDs and percentages match ZIMRA requirements
3. **Test API Endpoints**: Use a test environment to verify all endpoints work
4. **Validate Day Continuity**: Ensure previous day number is correct

### Post-Migration Testing
After completing migration:

1. **End-to-End Receipt Flow**: Test complete receipt submission process
2. **Fiscal Day Operations**: Verify open/close day functionality
3. **ZIMRA Integration**: Confirm receipts are properly submitted to ZIMRA
4. **Data Integrity**: Verify fiscal counters and day numbering

### Troubleshooting Common Migration Issues

#### Certificate Issues
- **Problem**: "Certificate not found" errors
- **Solution**: Verify certificate files are uploaded correctly via Django admin
- **Check**: Ensure certificate and key files match and are valid

#### Day Numbering Issues
- **Problem**: Incorrect fiscal day numbering
- **Solution**: Verify previous day record has correct `day_no`
- **Check**: Only ONE previous day record should exist

#### Tax Configuration Issues
- **Problem**: "Tax not found" errors
- **Solution**: Ensure tax names and IDs exactly match ZIMRA requirements
- **Check**: Use `GET /api/taxes/` to verify loaded taxes

#### Configuration Issues
- **Problem**: Missing device configuration
- **Solution**: Complete Step 2 migration setup thoroughly
- **Check**: Use `GET /api/configuration/` to verify setup

## Support

For migration-specific issues:
- **Internal Documentation**: Check your existing ZIMRA system documentation
- **Certificate Issues**: Contact your ZIMRA certificate provider
- **API Issues**: Refer to this documentation and test endpoints
- **Database Issues**: Check Django admin for data integrity

For general FiscGuy library issues:
- Email: cassymyo@gmail.com
- Issues: https://github.com/cassymyo-spec/zimra/issues
- Documentation: See README.md, INSTALL.md
