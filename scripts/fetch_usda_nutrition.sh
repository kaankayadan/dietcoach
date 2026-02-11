#!/bin/bash
# =============================================================================
# USDA FoodData Central API - Nutrition Data Fetcher
# =============================================================================
# Fetches per-100g nutrition data (kcal, protein, fat, carbs, fiber)
# for 85 common foods from the USDA FoodData Central API.
#
# API: https://api.nal.usda.gov/fdc/v1/foods/search
# Data Type: Survey (FNDDS) - these are the most practical food entries
#
# Nutrient IDs:
#   1008 = Energy (kcal)
#   1003 = Protein (g)
#   1004 = Total lipid / fat (g)
#   1005 = Carbohydrate, by difference (g)
#   1079 = Fiber, total dietary (g)
#
# Usage: API_KEY=your_key ./fetch_usda_nutrition.sh
# =============================================================================

API_KEY="${API_KEY:?Set API_KEY environment variable (get one at https://fdc.nal.usda.gov/api-key-signup)}"
BASE_URL="https://api.nal.usda.gov/fdc/v1/foods/search"
OUTPUT_FILE="usda_nutrition_results.json"

# All 85 foods to search
declare -a FOODS=(
  # BATCH 1 - Proteins
  "chicken breast cooked skinless"
  "turkey breast cooked"
  "ground beef cooked"
  "lamb cooked lean"
  "salmon cooked"
  "sea bass cooked"
  "tuna canned in water"
  "anchovy raw"
  "shrimp cooked"
  "egg whole cooked"
  "tofu firm"
  # BATCH 2 - Dairy
  "feta cheese"
  "cottage cheese low fat"
  "greek yogurt"
  "whole milk"
  "kefir"
  # BATCH 3 - Grains/Carbs
  "white rice cooked"
  "bulgur cooked"
  "pasta cooked"
  "whole wheat bread"
  "oatmeal cooked"
  "quinoa cooked"
  "potato boiled"
  "sweet potato baked"
  "chickpeas cooked"
  "lentils cooked"
  "kidney beans cooked"
  "granola"
  # BATCH 4 - Vegetables
  "broccoli cooked"
  "spinach raw"
  "tomato raw"
  "cucumber raw"
  "bell pepper raw"
  "onion raw"
  "carrot raw"
  "zucchini raw"
  "eggplant cooked"
  "cauliflower raw"
  "corn cooked"
  "avocado raw"
  "green beans cooked"
  "cabbage raw"
  "mushroom raw"
  # BATCH 5 - Fruits
  "apple raw"
  "banana raw"
  "orange raw"
  "strawberry raw"
  "raspberry raw"
  "blueberry raw"
  "kiwi raw"
  "grape raw"
  "watermelon raw"
  "pear raw"
  "peach raw"
  "cherry raw"
  "pineapple raw"
  "mango raw"
  "pomegranate raw"
  # BATCH 6 - Dried Fruits & Nuts
  "dried apricot"
  "dried fig"
  "dates"
  "raisins"
  "almonds"
  "walnuts"
  "hazelnuts"
  "peanuts roasted"
  "peanut butter"
  "cashews"
  "pistachios"
  "sunflower seeds"
  "flaxseed"
  "chia seeds"
  # BATCH 7 - Other
  "olive oil"
  "butter"
  "honey"
  "tahini"
  "hummus"
  "olives"
  "protein powder whey"
  "coconut oil"
  "dark chocolate"
  "pumpkin seeds"
  "rice cake"
  "tortilla flour"
  "flatbread"
)

echo "{"
echo "  \"foods\": ["

TOTAL=${#FOODS[@]}
COUNT=0

for food in "${FOODS[@]}"; do
  COUNT=$((COUNT + 1))
  # URL-encode the query
  QUERY=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$food'))")

  URL="${BASE_URL}?api_key=${API_KEY}&query=${QUERY}&dataType=Survey%20(FNDDS)&pageSize=1"

  echo "  Fetching [$COUNT/$TOTAL]: $food ..." >&2

  RESPONSE=$(curl -s "$URL")

  # Extract nutrients using python
  RESULT=$(echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
foods = data.get('foods', [])
if not foods:
    print(json.dumps({'food': '$food', 'error': 'not found'}))
    sys.exit(0)
f = foods[0]
desc = f.get('description', '')
nutrients = {n['nutrientId']: n.get('value', 0) for n in f.get('foodNutrients', [])}
result = {
    'search_query': '$food',
    'usda_description': desc,
    'per_100g': {
        'kcal': nutrients.get(1008, 0),
        'protein_g': nutrients.get(1003, 0),
        'fat_g': nutrients.get(1004, 0),
        'carb_g': nutrients.get(1005, 0),
        'fiber_g': nutrients.get(1079, 0)
    }
}
print(json.dumps(result))
")

  if [ "$COUNT" -lt "$TOTAL" ]; then
    echo "    $RESULT,"
  else
    echo "    $RESULT"
  fi

  # Rate limit: small delay between requests
  sleep 0.5
done

echo "  ]"
echo "}"

echo "" >&2
echo "Done! Fetched nutrition data for $TOTAL foods." >&2
