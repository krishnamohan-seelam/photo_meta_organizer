"""The fixed vocabulary of labels the AI can suggest (ADR-002 decision 7).

Curated for a personal photo library: places and scenes, nature, weather and light, animals,
food, people and activities, events, buildings, vehicles and everyday objects. Each label is a
short, lowercase noun phrase that reads naturally in "a photo of <label>" (the zero-shot prompt)
and as a tag a person would actually keep. Order is irrelevant to ranking; grouping is for
maintenance only. A label that is not here can never be suggested, so additions are cheap and
safe: they only take effect on the next analysis.
"""

_SCENES = """
beach, sea, ocean, coast, lake, river, waterfall, pond, harbor, marina, pier, island, bay,
cliff, cave, desert, sand dunes, canyon, valley, hills, mountain, mountain peak, glacier,
volcano, forest, jungle, meadow, field, farm, vineyard, orchard, garden, park, playground,
countryside, village, small town, city, city skyline, downtown, street, alley, crosswalk,
market, bazaar, square, plaza, bridge, tunnel, highway, railway, train station, airport, bus
stop, harbor town, campsite, trail, hiking path, ski slope, swimming pool, stadium, arena, zoo,
aquarium, museum, library, theater, concert hall, shopping mall, restaurant, cafe, bar, kitchen,
living room, bedroom, bathroom, balcony, rooftop, office, classroom, hospital, church interior,
temple interior, hotel room, lobby, staircase, hallway, garage, backyard, courtyard, terrace,
lighthouse, windmill, ruins, castle, palace
""".strip()

_NATURE_AND_WEATHER = """
sunrise, sunset, golden hour, blue hour, twilight, night sky, stars, milky way, moon, full moon,
eclipse, aurora, clouds, cloudy sky, blue sky, storm, lightning, rain, fog, mist, snow,
snowfall, frost, ice, rainbow, sunbeams, reflection, silhouette, shadows, wind, autumn leaves,
fall colors, spring blossoms, cherry blossoms, wildflowers, flowers, rose, tulips, sunflower,
lavender, cactus, palm trees, pine trees, oak tree, tree, bonsai, moss, ferns, grass, rocks,
pebbles, seashell, waves, surf, tide pools, stream, rapids, hot spring, geyser, swamp, tundra,
savanna, coral reef, underwater, night lights, long exposure, fireworks, campfire, bonfire
""".strip()

_ANIMALS = """
dog, puppy, cat, kitten, horse, pony, cow, sheep, lamb, goat, pig, chicken, rooster, duck,
goose, swan, turkey, rabbit, hamster, guinea pig, parrot, bird, eagle, owl, hawk, seagull,
pigeon, sparrow, hummingbird, peacock, flamingo, penguin, deer, fox, wolf, bear, polar bear,
squirrel, raccoon, monkey, gorilla, elephant, giraffe, zebra, lion, tiger, leopard, cheetah,
hippopotamus, rhinoceros, kangaroo, koala, panda, camel, whale, dolphin, seal, shark, fish,
turtle, frog, lizard, snake, crocodile, butterfly, bee, ladybug, dragonfly, spider, insect,
jellyfish, starfish, crab, lobster, octopus
""".strip()

_FOOD = """
food, meal, breakfast, lunch, dinner, dessert, cake, birthday cake, cupcakes, cookies,
chocolate, ice cream, pie, pastry, bread, pizza, pasta, burger, sandwich, sushi, ramen, noodles,
rice bowl, curry, steak, barbecue, seafood, salad, soup, eggs, pancakes, waffles, fruit, apples,
oranges, berries, strawberries, grapes, watermelon, vegetables, tomatoes, cheese, wine, beer,
cocktail, coffee, latte art, tea, juice, street food, picnic, farmers market, bakery, candy
""".strip()

_PEOPLE_AND_ACTIVITIES = """
portrait, selfie, group photo, family, couple, wedding, bride and groom, baby, toddler, children
playing, kids, teenagers, friends, crowd, audience, people walking, man, woman, elderly person,
child, dancing, singing, playing guitar, playing piano, concert, live music, band, running,
jogging, cycling, hiking, climbing, camping, fishing, swimming, surfing, snorkeling, diving,
skiing, snowboarding, skating, yoga, gym workout, soccer, football, basketball, baseball,
tennis, golf, cricket, swimming race, marathon, martial arts, horse riding, sailing, kayaking,
paddleboarding, skateboarding, picnic with friends, cooking, baking, shopping, reading, writing,
drawing, photographer, traveler, tourist, street performer, parade, festival, protest
""".strip()

_EVENTS = """
birthday party, graduation, christmas, christmas tree, halloween, thanksgiving, easter, new year
celebration, diwali, holi, lantern festival, carnival, wedding ceremony, baby shower, funeral,
anniversary, reunion, school event, sports event, competition, award ceremony, conference,
meeting, presentation, exhibition, art show, fair, circus, fireworks display, road trip,
vacation, holiday travel, business trip, moving house, renovation
""".strip()

_BUILDINGS_AND_VEHICLES = """
building, skyscraper, house, apartment building, cottage, cabin, barn, church, cathedral,
mosque, temple, shrine, pagoda, monastery, synagogue, tower, clock tower, statue, monument,
fountain, arch, gate, fence, wall, door, window, roof, chimney, bridge at night, old town,
historic building, modern architecture, glass facade, interior design, car, sports car, vintage
car, truck, bus, bicycle, motorcycle, scooter, taxi, train, tram, subway, airplane, helicopter,
boat, sailboat, yacht, ferry, cruise ship, canoe, tractor, ambulance, fire truck, police car,
hot air balloon, drone, spaceship
""".strip()

_OBJECTS_AND_MISC = """
document, receipt, screenshot, text, sign, poster, book, newspaper, map, whiteboard, painting,
sculpture, graffiti, mural, street art, craft, pottery, jewelry, clothing, shoes, bag, hat,
sunglasses, watch, toy, doll, lego, board game, playing cards, musical instrument, guitar,
piano, drums, camera, laptop, computer, smartphone, television, headphones, tools, plants in
pots, candle, lamp, mirror, furniture, sofa, bed, table, chair, bookshelf, christmas lights,
balloon, gift, flowers bouquet, cake with candles, trophy, medal, flag, umbrella, suitcase,
backpack, tent, sleeping bag, binoculars, telescope, microscope, black and white, macro,
close-up, aerial view, panorama, abstract, pattern, texture, minimal, blurry, motion blur,
bokeh, night photography
""".strip()


def _split(block: str) -> list[str]:
    return [label.strip() for label in block.replace("\n", " ").split(",") if label.strip()]


def _build() -> tuple[str, ...]:
    labels: list[str] = []
    for block in (
        _SCENES,
        _NATURE_AND_WEATHER,
        _ANIMALS,
        _FOOD,
        _PEOPLE_AND_ACTIVITIES,
        _EVENTS,
        _BUILDINGS_AND_VEHICLES,
        _OBJECTS_AND_MISC,
    ):
        labels.extend(_split(block))
    # De-duplicated, keeping the first occurrence: a label listed under two groups counts once.
    return tuple(dict.fromkeys(labels))


VOCABULARY: tuple[str, ...] = _build()
