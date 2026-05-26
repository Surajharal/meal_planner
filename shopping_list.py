from sqlalchemy.orm import Session
from ingredient_manager import IngredientManager
from typing import Dict, List
from collections import defaultdict
from database import get_manual_shopping_items, get_week_start_date
from delivery_links import delivery_app_home_links, delivery_search_links

class ShoppingListGenerator:
    def __init__(self, db: Session):
        self.db = db
        self.ingredient_manager = IngredientManager(db)
    
    def generate_shopping_list(self, user_id: int, week_start_date=None) -> Dict:
        """Generate a consolidated shopping list for this user's week."""
        if week_start_date is None:
            week_start_date = get_week_start_date()
        
        comparison = self.ingredient_manager.compare_required_vs_available(
            user_id, week_start_date
        )
        
        # Combine missing and partial items
        shopping_items = {}
        
        # Add missing items
        for name, data in comparison['missing'].items():
            category = data['category']
            if category not in shopping_items:
                shopping_items[category] = []
            
            shopping_items[category].append({
                'name': data['name'],
                'quantity': data['quantity'],
                'unit': data['unit'],
                'status': 'missing',
                'delivery_links': delivery_search_links(data['name']),
            })
        
        # Add partial items (only the needed quantity)
        for name, data in comparison['partial'].items():
            category = data['category']
            if category not in shopping_items:
                shopping_items[category] = []
            
            needed_qty = data.get('needed_quantity', data['quantity'])
            shopping_items[category].append({
                'name': data['name'],
                'quantity': needed_qty,
                'unit': data['unit'],
                'status': 'partial',
                'available_quantity': data.get('available_quantity', 0),
                'delivery_links': delivery_search_links(data['name']),
            })

        manual_count = 0
        for item in get_manual_shopping_items(self.db, user_id, week_start_date):
            category = item.category or 'other'
            if category not in shopping_items:
                shopping_items[category] = []

            shopping_items[category].append({
                'name': item.name,
                'quantity': item.quantity,
                'unit': item.unit,
                'status': 'manual',
                'manual_id': item.id,
                'delivery_links': delivery_search_links(item.name),
            })
            manual_count += 1
        
        # Sort categories and items
        sorted_categories = sorted(shopping_items.keys())
        for category in sorted_categories:
            shopping_items[category].sort(key=lambda x: x['name'])
        
        return {
            'items_by_category': shopping_items,
            'total_items': sum(len(items) for items in shopping_items.values()),
            'categories': sorted_categories,
            'delivery_home_links': delivery_app_home_links(),
            'summary': {
                'missing_count': comparison['missing_count'],
                'partial_count': comparison['partial_count'],
                'manual_count': manual_count,
                'total_required': comparison['required_total']
            }
        }
    
    def get_shopping_list_summary(self, user_id: int, week_start_date=None) -> Dict:
        """Get a summary of the shopping list for this user."""
        shopping_list = self.generate_shopping_list(user_id, week_start_date)
        
        total_quantity = 0
        for category_items in shopping_list['items_by_category'].values():
            for item in category_items:
                total_quantity += item['quantity']
        
        return {
            'total_categories': len(shopping_list['categories']),
            'total_items': shopping_list['total_items'],
            'total_quantity': total_quantity,
            'summary': shopping_list['summary']
        }
