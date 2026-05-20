from sqlalchemy.orm import Session
from database import (
    get_weekly_meals, get_recipe_by_id, update_inventory,
    get_weekly_inventory, get_ingredient_by_id, get_all_ingredients
)
from typing import Dict, List
from collections import defaultdict
from database import get_week_start_date

class IngredientManager:
    def __init__(self, db: Session):
        self.db = db
    
    def get_required_ingredients_for_week(
        self, user_id: int, week_start_date=None
    ) -> Dict:
        """Get all required ingredients for this user's week with quantities."""
        if week_start_date is None:
            week_start_date = get_week_start_date()
        
        meals = get_weekly_meals(self.db, user_id, week_start_date)
        required = defaultdict(lambda: {'quantity': 0, 'unit': '', 'category': ''})
        
        for meal in meals:
            if not meal.recipe_id:
                continue
            
            recipe = get_recipe_by_id(self.db, meal.recipe_id)
            if not recipe:
                continue
            
            # Calculate scaling factor based on servings
            scale_factor = meal.servings / recipe.servings if recipe.servings > 0 else 1
            
            for ri in recipe.ingredients:
                ing = ri.ingredient
                key = ing.name.lower()
                
                if key not in required or required[key]['quantity'] == 0:
                    required[key] = {
                        'ingredient_id': ing.id,
                        'name': ing.name,
                        'quantity': ri.quantity * scale_factor,
                        'unit': ri.unit,
                        'category': ing.category
                    }
                else:
                    # Add to existing quantity if same unit
                    if required[key]['unit'] == ri.unit:
                        required[key]['quantity'] += ri.quantity * scale_factor
                    else:
                        # Different units - keep both or convert (simplified: just add)
                        required[key]['quantity'] += ri.quantity * scale_factor
        
        return dict(required)
    
    def get_available_ingredients(self, week_start_date=None) -> Dict:
        """Get all available ingredients from inventory"""
        if week_start_date is None:
            week_start_date = get_week_start_date()
        
        inventory_items = get_weekly_inventory(self.db, week_start_date)
        available = {}
        
        for inv in inventory_items:
            if inv.available and inv.quantity > 0:
                available[inv.ingredient_id] = {
                    'ingredient_id': inv.ingredient_id,
                    'quantity': inv.quantity,
                    'unit': inv.unit,
                    'name': inv.ingredient.name
                }
        
        return available
    
    def compare_required_vs_available(
        self, user_id: int, week_start_date=None
    ) -> Dict:
        """Compare required ingredients with available inventory for this user's plan."""
        required = self.get_required_ingredients_for_week(user_id, week_start_date)
        available = self.get_available_ingredients(week_start_date)
        
        missing = {}
        sufficient = {}
        partial = {}
        
        for name, req_data in required.items():
            ing_id = req_data['ingredient_id']
            req_qty = req_data['quantity']
            req_unit = req_data['unit']
            
            if ing_id in available:
                avail_qty = available[ing_id]['quantity']
                avail_unit = available[ing_id]['unit']
                
                # Simple comparison (assumes same unit for now)
                if avail_unit == req_unit:
                    if avail_qty >= req_qty:
                        sufficient[name] = {
                            **req_data,
                            'available_quantity': avail_qty,
                            'status': 'sufficient'
                        }
                    else:
                        partial[name] = {
                            **req_data,
                            'available_quantity': avail_qty,
                            'needed_quantity': req_qty - avail_qty,
                            'status': 'partial'
                        }
                else:
                    # Different units - mark as partial for manual review
                    partial[name] = {
                        **req_data,
                        'available_quantity': avail_qty,
                        'available_unit': avail_unit,
                        'status': 'partial_unit_mismatch'
                    }
            else:
                missing[name] = {
                    **req_data,
                    'status': 'missing'
                }
        
        return {
            'missing': missing,
            'partial': partial,
            'sufficient': sufficient,
            'required_total': len(required),
            'missing_count': len(missing),
            'partial_count': len(partial),
            'sufficient_count': len(sufficient)
        }
    
    def update_ingredient_availability(self, ingredient_id: int, quantity: float,
                                      unit: str, available: bool, week_start_date=None):
        """Update ingredient availability in inventory"""
        if week_start_date is None:
            week_start_date = get_week_start_date()
        
        return update_inventory(
            self.db,
            ingredient_id=ingredient_id,
            quantity=quantity,
            unit=unit,
            available=available,
            week_start_date=week_start_date
        )
    
    def get_ingredients_by_category(self) -> Dict[str, List]:
        """Get all ingredients grouped by category"""
        ingredients = get_all_ingredients(self.db)
        categorized = defaultdict(list)
        
        for ing in ingredients:
            categorized[ing.category].append({
                'id': ing.id,
                'name': ing.name,
                'default_unit': ing.default_unit
            })
        
        return dict(categorized)
