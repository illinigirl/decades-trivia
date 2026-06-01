"""Curated pop-culture source pages per decade (movies, TV, toys, music artists).

Year-aggregator pages ("1985 in film") are list-heavy and thin once tables are
stripped, but individual subject pages (a movie, show, toy, artist) are
prose-rich and famous — ideal pub-trivia material. We curate the iconic ones.

Kept broad but recognizable (a little challenge is fine; avoid the truly
obscure). Mis-dated entries self-correct: decade year-scoping in retrieval drops
a chunk whose only years fall outside the decade, so a title listed under the
wrong decade just won't surface there. Missing pages are skipped at ingestion.
"""

# Capped lower than full pages — we want each subject's notable facts, not its
# entire article.
SUBJECT_CAP = 14

MOVIES = {
    "60s": ["Psycho (1960 film)", "Lawrence of Arabia (film)", "Dr. Strangelove",
            "The Sound of Music (film)", "Mary Poppins (film)", "2001: A Space Odyssey",
            "The Graduate", "Bonnie and Clyde (film)", "Easy Rider", "Goldfinger (film)",
            "West Side Story (1961 film)", "The Jungle Book (1967 film)",
            "Planet of the Apes (1968 film)", "Rosemary's Baby (film)",
            "The Good, the Bad and the Ugly", "My Fair Lady (film)",
            "Breakfast at Tiffany's (film)", "Cleopatra (1963 film)",
            "The Pink Panther (1963 film)", "101 Dalmatians (1961 film)",
            "Dr. No (film)", "Butch Cassidy and the Sundance Kid", "The Apartment",
            "To Kill a Mockingbird (film)", "The Birds (film)",
            "Who's Afraid of Virginia Woolf? (film)", "Midnight Cowboy",
            "The Italian Job (1969 film)", "Night of the Living Dead",
            "The Magnificent Seven"],
    "70s": ["The Godfather", "The Godfather Part II", "Jaws (film)", "Star Wars (film)",
            "Rocky", "Apocalypse Now", "Taxi Driver", "A Clockwork Orange (film)",
            "The Exorcist", "One Flew Over the Cuckoo's Nest (film)", "Saturday Night Fever",
            "Grease (film)", "Alien (film)", "Close Encounters of the Third Kind",
            "Annie Hall", "Chinatown (1974 film)", "Halloween (1978 film)",
            "Superman (1978 film)", "The Deer Hunter", "Willy Wonka & the Chocolate Factory",
            "The French Connection (film)", "Carrie (1976 film)", "Network (film)",
            "Dirty Harry", "The Sting", "Young Frankenstein", "Blazing Saddles",
            "Monty Python and the Holy Grail", "Rocky II", "American Graffiti",
            "The Texas Chain Saw Massacre"],
    "80s": ["E.T. the Extra-Terrestrial", "Back to the Future", "Ghostbusters (1984 film)",
            "The Empire Strikes Back", "Return of the Jedi", "Raiders of the Lost Ark",
            "Top Gun", "The Breakfast Club", "Ferris Bueller's Day Off", "Die Hard",
            "Batman (1989 film)", "Beverly Hills Cop", "Dirty Dancing", "The Terminator",
            "Aliens (film)", "Rain Man", "The Goonies", "Gremlins", "Stand by Me (film)",
            "Platoon (film)", "Blade Runner", "Indiana Jones and the Temple of Doom",
            "Who Framed Roger Rabbit", "Coming to America", "The Karate Kid",
            "The Shining (film)", "Airplane!", "Fast Times at Ridgemont High",
            "Scarface (1983 film)", "Field of Dreams", "Full Metal Jacket",
            "Rocky IV", "Beetlejuice", "Big (film)", "Wall Street (1987 film)",
            "Nightmare on Elm Street", "Flashdance", "Rambo: First Blood",
            "The Little Mermaid (1989 film)", "When Harry Met Sally..."],
    "90s": ["Titanic (1997 film)", "Jurassic Park (film)", "Pulp Fiction", "Forrest Gump",
            "The Lion King", "The Silence of the Lambs (film)", "Terminator 2: Judgment Day",
            "Home Alone", "Toy Story", "The Matrix", "Saving Private Ryan", "Goodfellas",
            "Fargo (1996 film)", "The Shawshank Redemption", "Braveheart",
            "Independence Day (1996 film)", "The Sixth Sense", "Beauty and the Beast (1991 film)",
            "Aladdin (1992 Disney film)", "Scream (1996 film)", "The Blair Witch Project",
            "Good Will Hunting", "Men in Black (1997 film)", "American Beauty (1999 film)",
            "Dances with Wolves", "Ghost (1990 film)", "Mrs. Doubtfire", "Se7en",
            "Twister (1996 film)", "The Big Lebowski", "Fight Club", "The Truman Show",
            "Toy Story 2", "Apollo 13 (film)", "Dumb and Dumber", "Clueless (film)",
            "The Mask (1994 film)", "Speed (1994 film)", "Pretty Woman"],
    "00s": ["Avatar (2009 film)", "The Lord of the Rings: The Fellowship of the Ring",
            "The Lord of the Rings: The Return of the King", "The Dark Knight",
            "Gladiator (2000 film)", "Harry Potter and the Philosopher's Stone (film)",
            "Shrek", "Finding Nemo", "Pirates of the Caribbean: The Curse of the Black Pearl",
            "Spider-Man (2002 film)", "Slumdog Millionaire", "No Country for Old Men",
            "Inglourious Basterds", "Up (2009 film)", "WALL-E", "Mean Girls",
            "The Bourne Identity (2002 film)", "Brokeback Mountain", "The Incredibles",
            "Monsters, Inc.", "Kill Bill: Volume 1", "The Departed", "300 (film)",
            "Iron Man (2008 film)", "Transformers (film)", "The Hangover",
            "Million Dollar Baby", "Crash (2004 film)", "Juno (film)", "Borat",
            "Anchorman: The Legend of Ron Burgundy", "Napoleon Dynamite",
            "Cast Away", "Moulin Rouge!", "Twilight (2008 film)",
            "The Passion of the Christ", "Ratatouille (film)"],
}

TV_SHOWS = {
    "60s": ["The Andy Griffith Show", "Star Trek: The Original Series", "Bewitched",
            "The Twilight Zone (1959 TV series)", "Gilligan's Island", "The Beverly Hillbillies",
            "I Dream of Jeannie", "Batman (TV series)", "The Ed Sullivan Show", "Bonanza",
            "The Flintstones", "Get Smart", "Mister Rogers' Neighborhood",
            "The Dick Van Dyke Show", "Hogan's Heroes", "The Addams Family (1964 TV series)",
            "The Munsters", "Scooby-Doo, Where Are You!", "Lost in Space",
            "Mission: Impossible (1966 TV series)", "Gunsmoke", "Green Acres",
            "The Jetsons", "Rowan & Martin's Laugh-In"],
    "70s": ["All in the Family", "M*A*S*H (TV series)", "The Mary Tyler Moore Show",
            "Happy Days", "Saturday Night Live", "Sesame Street", "The Brady Bunch",
            "Three's Company", "Charlie's Angels", "Little House on the Prairie (TV series)",
            "Taxi (TV series)", "The Muppet Show", "Roots (1977 miniseries)", "Soul Train",
            "Sanford and Son", "The Six Million Dollar Man", "Wonder Woman (1975 TV series)",
            "Starsky & Hutch", "Welcome Back, Kotter", "Laverne & Shirley",
            "Good Times", "The Jeffersons", "Fantasy Island", "Columbo",
            "Schoolhouse Rock!"],
    "80s": ["Cheers", "The Cosby Show", "Family Ties", "Miami Vice", "Dallas (1978 TV series)",
            "Dynasty (1981 TV series)", "The Golden Girls", "Knight Rider", "The A-Team",
            "Magnum, P.I.", "Married... with Children", "Roseanne", "Full House", "ALF",
            "MacGyver (1985 TV series)", "The Oprah Winfrey Show", "Who's the Boss?",
            "Hill Street Blues", "Saved by the Bell", "The Wonder Years",
            "Growing Pains", "Murder, She Wrote", "Night Court", "Diff'rent Strokes",
            "The Facts of Life (TV series)", "21 Jump Street", "Thirtysomething",
            "Moonlighting (TV series)", "The Smurfs (1981 TV series)", "Punky Brewster"],
    "90s": ["Seinfeld", "Friends", "The Simpsons", "The Fresh Prince of Bel-Air",
            "ER (TV series)", "The X-Files", "Frasier", "Buffy the Vampire Slayer",
            "Beverly Hills, 90210", "Home Improvement (TV series)", "South Park",
            "Baywatch", "Twin Peaks", "Boy Meets World", "Rugrats", "Will & Grace",
            "Friends", "Dawson's Creek", "Married... with Children", "Family Matters",
            "Saved by the Bell", "Power Rangers", "Beavis and Butt-Head", "Mad About You",
            "The Drew Carey Show", "King of the Hill", "Sabrina the Teenage Witch (1996 TV series)",
            "Ally McBeal", "The Wonder Years", "Doug (TV series)"],
    "00s": ["The Sopranos", "Survivor (American TV series)", "American Idol",
            "Lost (2004 TV series)", "Grey's Anatomy", "The Office (American TV series)",
            "Breaking Bad", "CSI: Crime Scene Investigation", "24 (TV series)",
            "Desperate Housewives", "SpongeBob SquarePants", "Family Guy",
            "The Apprentice (American TV series)", "House (TV series)", "Mad Men",
            "The Amazing Race", "Dancing with the Stars", "Heroes (American TV series)",
            "How I Met Your Mother", "Prison Break", "Scrubs (TV series)",
            "Curb Your Enthusiasm", "The West Wing", "Sex and the City",
            "Entourage (2004 TV series)", "Deal or No Deal (American game show)",
            "Dora the Explorer", "Avatar: The Last Airbender", "It's Always Sunny in Philadelphia"],
}

TOYS = {
    "60s": ["Barbie", "G.I. Joe", "Etch A Sketch", "Easy-Bake Oven", "Twister (game)",
            "Hot Wheels", "Lego", "Slinky", "Operation (game)", "Spirograph",
            "Troll doll", "Mr. Potato Head", "Chatty Cathy", "Rock 'em Sock 'em Robots",
            "Lite-Brite", "See 'n Say", "Battleship (game)", "Major Matt Mason"],
    "70s": ["Stretch Armstrong", "Pet Rock", "Atari 2600", "Simon (game)",
            "Big Wheel (tricycle)", "Nerf", "Lite-Brite", "Weeble", "Dungeons & Dragons",
            "Speak & Spell (toy)", "Magna Doodle", "Uno (card game)", "Star Wars (toys)",
            "Connect Four", "Shrinky Dinks", "Hungry Hungry Hippos",
            "Evel Knievel (toy)", "Micronauts", "Mood ring"],
    "80s": ["Rubik's Cube", "Cabbage Patch Kids", "Transformers (toy line)",
            "Teenage Mutant Ninja Turtles", "He-Man and the Masters of the Universe",
            "My Little Pony", "Care Bears", "Trivial Pursuit", "Nintendo Entertainment System",
            "Game Boy", "Pac-Man", "Garbage Pail Kids", "Teddy Ruxpin", "Koosh ball",
            "Trapper Keeper", "Pound Puppies", "G.I. Joe: A Real American Hero",
            "Lego", "Pictionary", "Glo Worm", "Skip-It", "Power Wheels",
            "Polly Pocket", "Micro Machines", "Jenga"],
    "90s": ["Beanie Babies", "Tamagotchi", "Furby", "Milk caps (game)", "Super Soaker",
            "Pokémon Trading Card Game", "Tickle Me Elmo", "Nintendo 64",
            "PlayStation (console)", "Polly Pocket", "Sega Genesis", "Game Boy Color",
            "Mighty Morphin Power Rangers", "Beanie Baby", "Yo-Yo", "Sky Dancers",
            "Easy-Bake Oven", "Bop It", "Game Boy", "Nintendo Game Boy",
            "Virtual pet", "Crossfire (game)", "Moon shoes", "Talkboy"],
    "00s": ["Razor (scooter)", "Bratz", "Beyblade", "Webkinz", "Nintendo DS", "Wii",
            "Xbox", "PlayStation 2", "IPod", "Robosapien", "Heelys", "Bakugan",
            "Guitar Hero", "Nintendo GameCube", "Xbox 360", "PlayStation 3",
            "Nintendo Wii", "Silly Bandz", "Zhu Zhu Pets", "Tech Deck",
            "Pokémon", "Build-A-Bear Workshop", "Rock Band (video game)"],
}

MUSIC_ARTISTS = {
    "60s": ["The Beatles", "The Rolling Stones", "Bob Dylan", "Elvis Presley",
            "The Beach Boys", "The Supremes", "Jimi Hendrix", "The Doors", "Aretha Franklin",
            "Simon & Garfunkel", "The Who", "Marvin Gaye", "Johnny Cash",
            "Janis Joplin", "Otis Redding", "The Monkees", "Stevie Wonder",
            "James Brown", "Ray Charles", "The Byrds", "Creedence Clearwater Revival",
            "Frank Sinatra"],
    "70s": ["Led Zeppelin", "Pink Floyd", "Queen (band)", "ABBA", "Elton John",
            "David Bowie", "Fleetwood Mac", "Eagles (band)", "Bee Gees", "Bob Marley",
            "Black Sabbath", "Aerosmith", "The Jackson 5", "Earth, Wind & Fire",
            "Donna Summer", "Kiss (band)", "Bruce Springsteen", "Dolly Parton",
            "Stevie Wonder", "The Carpenters", "Marvin Gaye", "Rod Stewart"],
    "80s": ["Michael Jackson", "Madonna", "Prince (musician)", "Whitney Houston",
            "Bruce Springsteen", "U2", "Bon Jovi", "Guns N' Roses", "Run-DMC",
            "Cyndi Lauper", "Duran Duran", "Def Leppard", "Metallica", "Tina Turner",
            "Lionel Richie", "Phil Collins", "George Michael", "The Police (band)",
            "Janet Jackson", "Bobby Brown", "Cher", "Billy Joel"],
    "90s": ["Nirvana (band)", "Mariah Carey", "Whitney Houston", "Spice Girls",
            "Backstreet Boys", "Britney Spears", "Tupac Shakur", "The Notorious B.I.G.",
            "Pearl Jam", "Garth Brooks", "Celine Dion", "Dr. Dre", "Snoop Dogg",
            "Radiohead", "Green Day", "Oasis (band)", "TLC (group)", "Boyz II Men",
            "Alanis Morissette", "Shania Twain", "Red Hot Chili Peppers", "'N Sync"],
    "00s": ["Eminem", "Beyoncé", "Britney Spears", "Jay-Z", "Kanye West", "Coldplay",
            "Linkin Park", "OutKast", "Usher (musician)", "50 Cent", "Lady Gaga",
            "Rihanna", "Taylor Swift", "Justin Timberlake", "The Black Eyed Peas",
            "Avril Lavigne", "Alicia Keys", "Green Day", "Amy Winehouse", "Maroon 5",
            "Christina Aguilera", "Nelly"],
}


def popculture_pages(decade: str) -> list[tuple[str, str, int]]:
    """(category, wikipedia_title, chunk_cap) entries for a decade, deduped."""
    groups = [("Film", MOVIES), ("Television", TV_SHOWS),
              ("Toys & Fads", TOYS), ("Music", MUSIC_ARTISTS)]
    out: list[tuple[str, str, int]] = []
    seen: set[str] = set()
    for category, table in groups:
        for title in table.get(decade, []):
            if title in seen:
                continue
            seen.add(title)
            out.append((category, title, SUBJECT_CAP))
    return out
