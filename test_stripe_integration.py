#!/usr/bin/env python3
"""Comprehensive Stripe integration test for payment widget"""

from app import create_app
from app.services.stripe_service import StripeService
from app.services.wizard_widgets import StripePaymentWidget
from app.models import Settings
import stripe

app = create_app()
with app.app_context():
    print('═' * 70)
    print('STRIPE INTEGRATION TEST')
    print('═' * 70)
    print()

    # Check Stripe configuration
    print('1. Checking Stripe Configuration...')
    settings_dict = {s.key: s.value for s in Settings.query.all()}
    stripe_connected = settings_dict.get('stripe_connected') in ['True', 'true', '1', True]
    stripe_key = settings_dict.get('stripe_secret_key', '')

    print(f'   Stripe Connected: {stripe_connected}')
    print(f'   API Key Present: {"Yes" if stripe_key else "No"}')
    if stripe_key:
        print(f'   Key Prefix: {stripe_key[:7]}...')
    print()

    if not stripe_connected or not stripe_key:
        print('❌ Stripe not configured. Please:')
        print('   1. Go to Settings → Stripe')
        print('   2. Enter your Stripe API key')
        print('   3. Click Connect')
        print('═' * 70)
        exit(1)

    # Check StripeService
    print('2. Checking StripeService...')
    is_configured = StripeService.is_configured()
    print(f'   Service Configured: {is_configured}')
    print()

    # Fetch products from Stripe
    print('3. Fetching Products from Stripe API...')
    try:
        products = stripe.Product.list(active=True, limit=10)
        product_count = len(products.data)
        print(f'   Products Found: {product_count}')
        print()

        if product_count == 0:
            print('⚠️  No active products found in Stripe.')
            print('   Please create at least one product with pricing in Stripe Dashboard.')
            print('═' * 70)
            exit(0)

        # Show first 3 products
        print('   Product Details:')
        for i, product in enumerate(products.data[:3], 1):
            print(f'   {i}. {product.name}')
            print(f'      ID: {product.id}')

            # Get prices
            prices = stripe.Price.list(product=product.id, active=True, limit=3)
            for price in prices.data:
                amount = price.unit_amount / 100 if price.unit_amount else 0
                currency = price.currency.upper()
                price_str = f'${amount:.2f}' if currency == 'USD' else f'{amount:.2f} {currency}'

                if price.recurring:
                    interval = price.recurring.get('interval', 'month')
                    print(f'      Price: {price_str}/{interval} (ID: {price.id})')
                else:
                    print(f'      Price: {price_str} one-time (ID: {price.id})')
        print()

    except stripe.error.AuthenticationError as e:
        print(f'❌ Stripe Authentication Error: {e}')
        print('   Please check your API key in Settings → Stripe')
        print('═' * 70)
        exit(1)
    except Exception as e:
        print(f'❌ Error fetching products: {e}')
        print('═' * 70)
        exit(1)

    # Test Widget
    print('4. Testing Payment Widget...')
    widget = StripePaymentWidget()
    data = widget.get_data('plex')

    print(f'   Widget Configured: {data.get("stripe_configured")}')
    print(f'   Products in Widget: {len(data.get("products", []))}')
    print(f'   Checkout URL: {data.get("checkout_url")}')
    print()

    if data.get('products'):
        print('   Widget Product List:')
        for i, p in enumerate(data['products'][:3], 1):
            print(f'   {i}. {p["name"]} - {p["price_display"]}', end='')
            if p.get('recurring'):
                print(f'/{p["recurring_interval"]}')
            else:
                print()
    print()

    # Test widget rendering
    print('5. Testing Widget Render...')
    try:
        html = widget.render('plex', context={})
        html_size = len(html)
        has_cards = 'product-card' in html
        has_script = 'createCheckoutSession' in html

        print(f'   HTML Size: {html_size} characters')
        print(f'   Has Product Cards: {has_cards}')
        print(f'   Has Checkout Script: {has_script}')
        print()

        if html_size < 500:
            print('⚠️  HTML seems short - widget may not be rendering correctly')

    except Exception as e:
        print(f'❌ Widget render error: {e}')
        print()

    print('═' * 70)
    print('✅ STRIPE INTEGRATION TEST COMPLETE')
    print('═' * 70)
    print()
    print('Next Steps:')
    print('1. Create a test invitation with requires_payment=True')
    print('2. Add a wizard step that uses {{ widget:stripe_payment }}')
    print('3. Test the complete checkout flow')
    print('═' * 70)
