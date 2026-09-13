"""
Spark AI Wingman Service — Personal Dating Assistant Engine.
Provides:
1. Contextual Match Icebreakers (Profile & Interests based)
2. Conversation Revivers (for stalled / dead chats)
3. AI Profile Coach & Optimization Analyzer
4. Multi-tone support (Flirty, Funny, Respectful, Casual)
5. Multi-lingual support (Hinglish, Hindi, English)
6. Dual-layer engine: Gemini API (if GEMINI_API_KEY is present) + Local Smart Context Engine fallback.
"""

import os
import random
import json
import urllib.request
from typing import List, Dict, Optional, Any

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# ==============================================================================
# 1. SMART CONTEXTUAL ENGINE DATA & TEMPLATES
# ==============================================================================

INTEREST_TOPIC_MAP = {
    "coffee": {
        "hinglish": {
            "flirty": [
                "Coffee pasand hai ya direct mere sath cold brew date pe chalogi? ☕😉",
                "Cup of coffee aur tumhari baatein... sounds like a perfect evening ✨☕",
                "Warning: Meri coffee se zyada addicted tum ho sakti ho ☕😏",
            ],
            "funny": [
                "Coffee lover ho? Toh yeh batao, bina coffee ke insaan rehte ho ya zombie ban jaate ho? 🧟‍♂️☕",
                "Coffee first, baaki saari life ki tension baad me! Blue Tokai ya Starbucks? 😂",
                "Sach batana, coffee pasand hai ya bas aesthetic cafe pictures lena pasand hai? ☕📸",
            ],
            "respectful": [
                "Hey! Noticed you love coffee. Any favourite local cafe you’d recommend around here? ☕",
                "Hello! Always great to meet a fellow coffee enthusiast. What's your go-to brew? ☕😊",
                "Hi! Hope your day is going great. Are you more of a cappuccino or black coffee person? ☕",
            ],
            "casual": [
                "Hey! Chai vs Coffee debate me tumhara stand kya hai? ☕👀",
                "Cold coffee with ice cream ya classic espresso? Asking the real questions here! ☕",
                "Hey there, coffee addict spotted! Kaunsi coffee abhi tak ki best rahi hai? ☕",
            ]
        },
        "hindi": {
            "flirty": [
                "कॉफ़ी का बहाना और आपके साथ एक ख़ूबसूरत शाम... कैसा रहेगा? ☕✨",
                "कॉफ़ी तो अच्छी होती ही है, पर आपकी मुस्कान से दिन बन जाए। ☕😊",
            ],
            "funny": [
                "कॉफ़ी की तलब है या बस कैफ़े में बैठने का शौक़? सच बताइए! 😂☕",
                "दिन की शुरुआत कॉफ़ी से या नींद में ही आधा दिन गुज़रता है? ☕😴",
            ],
            "respectful": [
                "नमस्ते! आपकी प्रोफ़ाइल में देखा कि आपको कॉफ़ी पसंद है। आपका पसंदीदा कैफ़े कौन सा है? ☕",
                "हेलो! एक अच्छे कॉफ़ी लवर से मिलकर अच्छा लगा। आप कैपुचीनो पसंद करते हैं या ब्लैक कॉफ़ी? ☕😊",
            ],
            "casual": [
                "नमस्ते! चाय या कॉफ़ी, दोनों में आपका दिल किस पर आता है? ☕",
                "हेलो! कभी अच्छी फ़िल्टर कॉफ़ी ट्राई की है? ☕",
            ]
        },
        "english": {
            "flirty": [
                "I like my coffee like I like my matches—hot, sweet, and keeping me up at night 😉☕",
                "Coffee first, but dinner date next? What do you say? ✨☕",
            ],
            "funny": [
                "Are you a morning coffee person or a 'don't talk to me before 11 AM' person? 😂☕",
                "Coffee first, Hogwarts later? 😂☕",
            ],
            "respectful": [
                "Hey! Loved your profile. What’s your absolute favourite coffee spot in town? ☕😊",
                "Hi there! Always refreshing to meet someone who appreciates good coffee. Americano or Latte? ☕",
            ],
            "casual": [
                "Chai or Coffee—pick your side and defend your choice! ☕",
                "Hey! If we went for coffee, what’s your ultimate drink order? ☕",
            ]
        }
    },
    "travel": {
        "hinglish": {
            "flirty": [
                "Mountains pasand hai ya beach? Kyunki meri next trip partner tum lag rahi ho ✨🏖️",
                "Passport ready hai? Kyunki tumhare sath travel karna magical lag raha hai ✈️😉",
            ],
            "funny": [
                "Traveler ho? Bag pack karne me 10 minute lagte hain ya poora ghar utha ke le jaate ho? 😂🎒",
                "Mountains me shanti dhoondhte ho ya Reels banane jaate ho? Sach sach batana! 🏔️📸",
            ],
            "respectful": [
                "Hey! You seem to love traveling. What's the most breathtaking place you've visited so far? ✈️🏔️",
                "Hi! Inspiring travel photos. Which destination is currently at the top of your bucket list? 🗺️😊",
            ],
            "casual": [
                "Mountains or Beaches? Let the timeless battle begin! 🏖️⛰️",
                "Spontaneous road trip ya fully planned vacation? Tum kis category me aate ho? 🚗",
            ]
        },
        "hindi": {
            "flirty": [
                "पहाड़ों की वादियों में आपके साथ एक सफ़र हो जाए तो क्या बात है ✨🏔️",
                "सफ़र ख़ूबसूरत हो जाता है जब हमसफ़र ख़ास हो 😊✈️",
            ],
            "funny": [
                "ट्रैवल करने जाते हैं या सिर्फ़ इंस्टाग्राम के लिए फ़ोटो खिंचवाने? 😂📸",
                "पहाड़ बुला रहे हैं या सिर्फ़ मंडे की मीटिंग से भागना चाहते हैं? 🏔️😂",
            ],
            "respectful": [
                "नमस्ते! आपको घूमना पसंद है, अब तक की सबसे यादगार यात्रा कौन सी रही है? ✈️",
                "हेलो! आपकी अगली ड्रीम डेस्टिनेशन कौन सी है? 🗺️😊",
            ],
            "casual": [
                "पहाड़ या समुद्र का किनारा? आपका दिल कहाँ सुकून पाता है? 🏖️🏔️",
                "अचानक बना हुआ ट्रिप या पूरी प्लानिंग के साथ? 🚗",
            ]
        },
        "english": {
            "flirty": [
                "You’ve got that wanderlust look. Mind if I tag along on your next adventure? ✨✈️",
                "Mountains or beaches? Either way, you’re making the view look good 😉",
            ],
            "funny": [
                "Are you an 'on-time for the flight' traveler or a 'running through security barefoot' traveler? 😂🏃",
                "Travel bug detected! Do you actually unpack, or does the suitcase live on the floor? 🧳😂",
            ],
            "respectful": [
                "Hey! What’s one place you’ve traveled to that genuinely changed your perspective? ✈️🌍",
                "Hi! Amazing travel vibe on your profile. Where’s your next stop? 🗺️😊",
            ],
            "casual": [
                "Solo traveler or road trip with besties kind of vibe? 🚗✈️",
                "Top destination on your bucket list right now? 📍",
            ]
        }
    },
    "gym": {
        "hinglish": {
            "flirty": [
                "Gym routine toh strong hai, but kya tumhara dil bhi itna hi strong hai? 😉💪",
                "Cardio pasand hai? Kyunki tumhari profile dekh ke heartbeat waise hi fast ho gayi ✨🏋️",
            ],
            "funny": [
                "Leg day pe gym jaate ho ya chupke se skip maar dete ho? Sach batana! 😂🍗",
                "Gym jaate ho workout karne ya शीशे ke aage pump dekh ke selfies lene? 🤳💪",
            ],
            "respectful": [
                "Hey! Impressed by your fitness dedication. What’s your favourite workout routine? 🏋️‍♂️✨",
                "Hi! Consistency in fitness is admirable. How long have you been training? 💪😊",
            ],
            "casual": [
                "Pre-workout me coffee ya direct beast mode? ☕💪",
                "Gym playlist me Punjabi beats ya Phonk/Rock? What gets you pumped? 🎧🏋️",
            ]
        },
        "hindi": {
            "flirty": [
                "फ़िटनेस का शौक़ तो कमाल है, और आपकी मुस्कान उससे भी बेहतर 😊💪",
            ],
            "funny": [
                "लेग डे से डर लगता है या बहादुरी से करते हैं? सच बताइए! 😂",
            ],
            "respectful": [
                "नमस्ते! आपकी फ़िटनेस के प्रति लगन तारीफ़ के क़ाबिल है। आप कब से वर्कआउट कर रहे हैं? 💪",
            ],
            "casual": [
                "वर्कआउट के साथ म्यूज़िक कौन सा सुनते हैं? 🎧",
            ]
        },
        "english": {
            "flirty": [
                "Is it cardio day? Because my heart did a double take when I saw your profile 😉💪",
            ],
            "funny": [
                "Be honest: do you actually like burpees or is that just an urban myth? 😂",
            ],
            "respectful": [
                "Hey! Great to see someone passionate about fitness. What’s your current goal? 🏋️‍♂️✨",
            ],
            "casual": [
                "Gym playlist check: EDM, Hip-Hop, or heavy metal? 🎧💪",
            ]
        }
    },
    "foodie": {
        "hinglish": {
            "flirty": [
                "Pehle pet pooja, fir prem duja... dinner date pe chalein? 🍕✨😉",
                "Foodie ho? Fir toh meri favourite dish tumhare sath share karne ka mann kar raha hai 🍝😋",
            ],
            "funny": [
                "Pani Puri ka paani teekha ya meetha? Is question pe humari dosti depend karegi! 😂🍲",
                "Momos with extra spicy red chutney ya zero spice? Reveal your truth! 🥟🌶️",
            ],
            "respectful": [
                "Hey! A fellow foodie! What’s your comfort street food spot that never disappoints? 🍜😊",
                "Hi! If you could only eat one cuisine for the rest of your life, what would it be? 🍕🌮",
            ],
            "casual": [
                "Late night food cravings me Maggi ya Swiggy order? 🍜🌙",
                "Pizza crust chhodte ho ya poora kha jaate ho? Important question! 🍕😂",
            ]
        },
        "hindi": {
            "flirty": [
                "खाने के शौक़ीन हैं तो चलिए कभी एक ख़ास डिनर पर मिलते हैं 🍝✨",
            ],
            "funny": [
                "गोलगप्पे का पानी तीखा पसंद है या मीठा? सोच समझकर बताइएगा! 😂🍲",
            ],
            "respectful": [
                "नमस्ते! आपकी प्रोफ़ाइल देखकर लगा आप खाने के शौक़ीन हैं। आपका पसंदीदा व्यंजन क्या है? 🍜",
            ],
            "casual": [
                "देर रात की भूख में मैगी या जोमैटो? 🍜😋",
            ]
        },
        "english": {
            "flirty": [
                "They say the way to the heart is through food... care to test that theory on a dinner date? 🍝✨",
            ],
            "funny": [
                "Do you share food, or are you in the 'Joey doesn't share food' club? 😂🍕",
            ],
            "respectful": [
                "Hey! What’s the ultimate hidden gem restaurant you recommend to everyone? 🍜✨",
            ],
            "casual": [
                "Street food or fine dining? Where does your soul truly belong? 🌮✨",
            ]
        }
    },
    "movies": {
        "hinglish": {
            "flirty": [
                "Movie nights with popcorn and cuddles... ya Marvel marathon with deep talks? 🎬🍿✨",
                "Tumhara movie taste dekh ke lagta hai humari script pehle se written thi 😉🎞️",
            ],
            "funny": [
                "Movie dekhte waqt beech me questions poochne walo me se ho ya silent watcher? 😂🤫",
                "Binge-watching me 'Just one more episode' bol ke subah 4 baje tak jaagne ka record hai? 🥱🍿",
            ],
            "respectful": [
                "Hey! Noticed your passion for cinema. What's one movie you could rewatch anytime? 🎬😊",
                "Hi! What’s your take on recent Bollywood/Hollywood releases? Anything worth watching? 🍿🎥",
            ],
            "casual": [
                "Comfort movie/series batao jo sad mood me instantly theek kar deti hai! 🎬🍿",
                "Horror movies dekh ke dar lagta hai ya popcorn khao aur haso? 👻🍿",
            ]
        },
        "hindi": {
            "flirty": [
                "फ़िल्मों का शौक़ है तो कभी साथ में पॉपकॉर्न और एक अच्छी फ़िल्म हो जाए? 🍿🎬",
            ],
            "funny": [
                "फ़िल्म देखते वक़्त बीच में सवाल पूछने की आदत तो नहीं है आपकी? 😂🤫",
            ],
            "respectful": [
                "नमस्ते! आपकी पसंदीदा क्लासिक फ़िल्म कौन सी है जिसे आप बार-बार देख सकते हैं? 🎬",
            ],
            "casual": [
                "थ्रिलर फ़िल्में या रोमांटिक कॉमेडी? आपका मूड किस पर रहता है? 🍿🎥",
            ]
        },
        "english": {
            "flirty": [
                "Movie marathon on the couch—you bring the popcorn, I bring the charm 😉🍿",
            ],
            "funny": [
                "Are you a cinema snob or can you enjoy a delightfully trashy Bollywood/Hollywood film? 😂",
            ],
            "respectful": [
                "Hey! What’s the best movie you’ve watched this year so far? 🎬✨",
            ],
            "casual": [
                "If you had to recommend just ONE movie right now, what’s your pick? 🍿",
            ]
        }
    },
    "music": {
        "hinglish": {
            "flirty": [
                "Tumhara music taste dekh ke laga humari vibe naturally sync ho jayegi 🎵✨😉",
                "Ek romantic playlist banai hai... sunna chahogi mere sath? 🎧🎶",
            ],
            "funny": [
                "Shower singer ho ya car me full blast pe besura gaane ka confidence hai? 😂🚿🎤",
                "Spotify Wrapped dekh ke sharam aati hai ya proud feel hota hai? 😂🎧",
            ],
            "respectful": [
                "Hey! What’s on repeat on your headphones right now? Always looking for new tracks! 🎵✨",
                "Hi! Who is that one artist you can listen to anytime without skipping? 🎶😊",
            ],
            "casual": [
                "Arijit Singh at 2 AM ya AP Dhillon on highway? Pick your mood! 🚗🎵",
                "Concerts pasand hain ya acoustic cafe live sessions? 🎸🎤",
            ]
        },
        "hindi": {
            "flirty": [
                "संगीत की समझ और आपकी सादगी... दोनों ही दिल जीत लेते हैं 🎵✨",
            ],
            "funny": [
                "गाना सिर्फ़ बाथरूम में गाते हैं या कभी किसी को सुनाया भी है? 😂🎤",
            ],
            "respectful": [
                "नमस्ते! आपका सबसे पसंदीदा गायक या बैंड कौन सा है? 🎶",
            ],
            "casual": [
                "सूफ़ी संगीत या रेट्रो बॉलीवुड क्लासिक्स? 🎧✨",
            ]
        },
        "english": {
            "flirty": [
                "Send me your favourite song so I know how it feels inside your head 😉🎧",
            ],
            "funny": [
                "What’s your guilty pleasure song you’d never play in front of friends? 😂🎵",
            ],
            "respectful": [
                "Hey! What song is currently on heavy rotation on your Spotify? 🎧✨",
            ],
            "casual": [
                "Live gig in a packed stadium or cozy unplugged acoustic session? 🎸",
            ]
        }
    },
    "pets": {
        "hinglish": {
            "flirty": [
                "Doggos pasand hain? Good news: dog lovers naturally mere dil ke kareeb hote hain 🐕✨😉",
                "Kya tumhare pet se approval lena padega tumse milne ke liye? Ready for the test! 🐾😊",
            ],
            "funny": [
                "Sach batao, agar doggo ne mujhe reject kar diya toh humara koi future hai? 😂🐕",
                "Cute dog pictures send karne ki permit mil sakti hai yahan? 🐶📱",
            ],
            "respectful": [
                "Hey! Seeing pets on your profile instantly brought a smile. Do you have a furry friend? 🐾😊",
                "Hi! Pet parents are truly the kindest people. Tell me about your pet! 🐕✨",
            ],
            "casual": [
                "Dog person, Cat person, or overall animal lover? 🐕🐈",
                "Golden Retriever energy ya Black Cat energy? Tumhara kya vibe hai? 🐾",
            ]
        },
        "hindi": {
            "flirty": [
                "जानवरों से प्यार करने वाले लोग दिल के बहुत साफ़ होते हैं... जैसे आप 😊🐾",
            ],
            "funny": [
                "अगर आपके पालतू जानवर ने मुझे भौंक दिया तो क्या हमारी डेट कैंसिल हो जाएगी? 😂🐕",
            ],
            "respectful": [
                "नमस्ते! क्या आपके पास कोई पेट है? उनके बारे में कुछ बताइए! 🐾😊",
            ],
            "casual": [
                "कुत्ते या बिल्लियाँ, आपकी पहली पसंद कौन सी है? 🐕🐈",
            ]
        },
        "english": {
            "flirty": [
                "I hope your pet likes me, because I’m already planning on winning you both over 😉🐾",
            ],
            "funny": [
                "Will your dog approve of me, or do I need to bring treats to our first meeting? 😂🐶",
            ],
            "respectful": [
                "Hey! Animals on a profile are always the best green flag. Tell me about your pet! 🐾✨",
            ],
            "casual": [
                "Golden Retriever personality or moody cat energy? Where do you fall? 🐾😂",
            ]
        }
    },
    "gaming": {
        "hinglish": {
            "flirty": [
                "Game me harana aasan hai ya tumhare dil ko jeetna? Challenge accepted 😉🎮",
                "Player 2 mil gaya ya abhi bhi solo lobby me ho? 🎮✨",
            ],
            "funny": [
                "Match harne ke baad rage quit karte ho ya shanti se controller rakhte ho? 😂🎮",
                "Gaming skills achhi hain ya bas teammates ko blame karne me pro ho? 🕹️😂",
            ],
            "respectful": [
                "Hey! Fellow gamer spotted! What’s your all-time favourite game or console? 🎮✨",
                "Hi! What are you currently playing? Always looking for good recommendations! 🕹️😊",
            ],
            "casual": [
                "PC Master Race, PlayStation, or Mobile Gaming? Let's settle this! 🎮",
                "Co-op gaming nights ya competitive matchmaking? 🕹️",
            ]
        },
        "hindi": {
            "flirty": [
                "खेल में तो आप माहिर हैं, पर क्या दिल के खेल में भी जीतना पसंद है? 🎮😉",
            ],
            "funny": [
                "हारने पर गुस्सा आता है या आराम से पानी पीते हैं? 😂🎮",
            ],
            "respectful": [
                "नमस्ते! आपका पसंदीदा गेम कौन सा है? 🎮✨",
            ],
            "casual": [
                "मोबाइल गेमिंग या कंसोल? आपकी पसंद क्या है? 🕹️",
            ]
        },
        "english": {
            "flirty": [
                "Looks like I found my Player 2. Care for a 1v1 or are we teaming up? 😉🎮",
            ],
            "funny": [
                "Are you the carrying teammate or the one who panics and runs into walls? 😂🎮",
            ],
            "respectful": [
                "Hey! Great gaming taste. What’s the title you’ve put the most hours into? 🎮✨",
            ],
            "casual": [
                "Story-driven campaigns or frantic multiplayer lobbies? 🕹️",
            ]
        }
    }
}

# General Fallback Opening Lines (when specific interests aren't matched)
GENERAL_OPENERS = {
    "hinglish": {
        "flirty": [
            "Ek baat bolu? Tumhari profile picture dekh ke right swipe na karna crime hota ✨😉",
            "Mera day thoda boring tha, par humara match dekh ke seedha weekend vibe aa gayi! 😏✨",
            "Warning: Mere jokes par hasna padega, cute lagti ho has kar 😂✨",
            "Lagta hai universe ne hume match karake sabse sahi faisla kiya hai 😉",
        ],
        "funny": [
            "Hello! Hum match toh ho gaye, ab kya direct shadi ki shopping karein ya pehle 'Hi' bol lu? 😂",
            "Sach sach batana: profile bio kitni der sochte ho likhne se pehle? 1 ghanta ya 2 din? 😂",
            "Toh batao, pehla sawal kya hona chahiye—'Chai piyogi?' ya 'Life ka purpose kya hai?' 😂",
            "Humara match dekh ke algorithm bhi khush ho gaya hoga! Kaise ho? 🤖✨",
        ],
        "respectful": [
            "Hey! Your profile caught my eye—very warm and genuine vibe. How has your week been? 😊",
            "Hello! Lovely to connect with you here. Hope you're having a relaxing day! ✨",
            "Hi! Really liked your bio and aesthetic. What's been the highlight of your day so far? 😊",
            "Hello! Glad we matched. What kind of things do you enjoy doing on weekends? ✨",
        ],
        "casual": [
            "Hey! Sunday routine: bed se hilna nahi ya subah se active plan? 🛋️☕",
            "Two truths and a lie khelte hain! Tu pehle start kar ya main? 👀🎲",
            "Hey there! A quick question to break the ice: weekend pe best chill spot kaun sa hai? 📍",
            "Hello! Ek quick poll: online shopping cart me 50 items add karke bhool jaana pasand hai ya direct buy? 😂",
        ],
        "mysterious": [
            "Tumhare profile me ek aisi subtle baat notice ki maine jo 99% log miss kar dete hain... 🔮",
            "Ek prediction karu tumhare baare me? And trust me, meri predictions rarely galat hoti hain... 🌙",
            "Tumhari profile me ek ankahee story hai jo kaafi magnetic lag rahi hai... ✨",
            "Hum dono me ek aisi strange similarity hai jo tumne kabhi expect nahi ki hogi... guess karo? 🔮",
        ],
        "suspenseful": [
            "Mujhe tumse ek aisi cheez share karni hai jo shayad mujhe yahan open me nahi bolni chahiye thi... ⏳",
            "Tumse ek bohot zaroori sawal poochna hai... lekin promise karo 100% sach bologi? 🕵️‍♂️",
            "Is match ke baad ek plot twist aane wala hai... are you ready for it? ⏳⚡",
            "Maine tumhari photos dekh ke ek bada decision le liya hai... batau kya? 🤫",
        ]
    },
    "hindi": {
        "flirty": [
            "आपकी मुस्कान देखकर लगा कि आज का दिन ख़ास होने वाला है ✨😊",
            "इत्तेफ़ाक़ भी बड़े ख़ूबसूरत होते हैं, जैसे हमारा यहाँ मैच होना 😉✨",
        ],
        "funny": [
            "नमस्ते! मैच तो हो गया, अब बातचीत की शुरुआत 'हाय' से करें या किसी अच्छे जोक से? 😂",
            "क्या आप भी उन लोगों में से हैं जो मैसेज टाइप करके 5 बार मिटाते हैं? 😂",
        ],
        "respectful": [
            "नमस्ते! आपकी प्रोफ़ाइल बहुत ही शालीन और ख़ूबसूरत लगी। आपका दिन कैसा गुज़र रहा है? 😊",
            "हेलो! आपसे जुड़कर बहुत अच्छा लगा। उम्मीद है आपका हफ़्ता शानदार बीता होगा। ✨",
        ],
        "casual": [
            "नमस्ते! वीकेंड पर आराम करना पसंद है या दोस्तों के साथ बाहर जाना? ☕",
            "हेलो! एक बात बताइए, चाय की चुस्की या कॉफ़ी की महक? ☕",
        ],
        "mysterious": [
            "आपकी प्रोफ़ाइल में एक ऐसा राज़ महसूस हुआ जो हर किसी की नज़र में नहीं आता... 🔮",
            "क्या मैं आपके व्यक्तित्व के बारे में एक गहरा सच बताऊँ? हैरान रह जाएँगी आप 🌙",
            "आपकी आँखों में एक अनकही कहानी है जो काफ़ी दिलचस्प और ख़ास लग रही है ✨",
        ],
        "suspenseful": [
            "मुझे आपसे एक बेहद ज़रूरी सवाल पूछना है... पर वादा कीजिए सच बताएँगी? ⏳",
            "अगर मैं आपको एक ऐसा सच बताऊँ जो सिर्फ़ मुझे पता है, तो क्या आप संभाल पाएँगी? 🤫",
            "हमारी इस बातचीत में एक बहुत बड़ा मोड़ आने वाला है... क्या आप तैयार हैं? ⏳⚡",
        ]
    },
    "english": {
        "flirty": [
            "Not gonna lie, your smile stopped my endless swiping instantly ✨😉",
            "Are we about to be the cutest couple on this app, or should we take it slow? 😏✨",
            "I was having an average Tuesday until our match popped up. How's your evening? ✨",
        ],
        "funny": [
            "Our match is here! Do we do the awkward 'Hey' or skip straight to debating pizza toppings? 😂🍕",
            "Tell me the truth: how long did it take you to pick your profile pictures? 😂📸",
            "Algorithm did its job, now the pressure is on us not to be boring! 😂 Ready?",
        ],
        "respectful": [
            "Hey! Your profile has such a refreshing and genuine warmth to it. How’s your week going? 😊",
            "Hello! Great to connect with you. What’s something exciting that happened in your world lately? ✨",
            "Hi! Loved your photos and prompts. What’s keeping you busy these days? 😊",
        ],
        "casual": [
            "Two truths and a lie to break the ice—who goes first? 🎲👀",
            "Quick personality test: are you a spontaneous planner or a detailed itinerary person? 🗺️",
            "Sunday vibe check: cozy blanket and Netflix, or outdoor café exploring? ☕",
        ],
        "mysterious": [
            "I noticed a very specific detail in your profile that 99% of people probably scroll past... 🔮",
            "I have a theory about you based on just your vibe, and I'm rarely wrong. Want to hear it? 🌙",
            "You have this quiet energy that feels like an unread book with all the best chapters hidden ✨",
            "There's something wonderfully intriguing about you that caught my attention instantly... 🔮",
        ],
        "suspenseful": [
            "I need to ask you one question, but promise you'll answer with ruthless honesty... ⏳",
            "I was debating whether to message you this or keep it to myself... but here goes 🤫",
            "There is a 50/50 chance this conversation either starts an adventure or ruins my reputation 😂⏳",
            "Our match triggered an interesting sequence of events... care to know the plot twist? ⚡",
        ]
    }
}

# Conversation Reviver Follow-up Suggestions (when conversation is dead / stalled)
REVIVE_SUGGESTIONS = {
    "hinglish": {
        "flirty": [
            "Lagta hai humari chat thodi freeze ho gayi hai... chalo thoda spark add karte hain 🔥😉",
            "Main busy tha ya tum mujhe miss kar rahi thi? (I know the answer 😏)",
            "Ek baat admit karu? Tumhara notification miss kar raha tha ✨",
            "Conversation thodi chup ho gayi... chalo ice melt karte hain with a quick fun game? 😉",
        ],
        "funny": [
            "Lagta hai tumhara phone astronaut ne Mars pe bhej diya hai! Wapas aa gaya? 🚀😂",
            "Hello? Ghost ho gaye ya Netflix binge me beh gaye? Ek sign do agar zinda ho! 👻😂",
            "Yeh silence itna serious hai ki background me sad violin music bajne laga hai 🎻😂",
            "Quick question: kidnappers ne chhoda ya phone charge pe lagana bhool gaye the? 😂🔋",
        ],
        "respectful": [
            "Hey! Hope you're having a productive week. No pressure at all, just thought I'd check in and see how things are going! 😊",
            "Hello! I know how hectic life can get. Hope work and everything is treating you well! ✨",
            "Hey! Saw something today that reminded me of our chat. Hope your week is going smoothly! 😊",
        ],
        "casual": [
            "Hey! Ek random thought aaya and wanted your take on it 👀",
            "Chat revive protocol activated 🚨! Batao weekend ka kya plan chal raha hai?",
            "Busy week ya chill vibes? Aaj kal kya chal raha hai tumhari side? ☕",
        ],
        "mysterious": [
            "Silence hamesha sabse bada jawab hoti hai... par tumhari silence ka matlab kya samjhu? 🔮",
            "Lagta hai tum ek mystery banne ki koshish kar rahi ho... and to be honest, it's actually working 😉🌙",
            "Tumhare baare me ek thought aaya tha aaj subah, par tab tak nahi bataunga jab tak reply na aaye 🤫",
        ],
        "suspenseful": [
            "Tumhara aakhri message ek aisi suspense thriller pe ruka hai ki cliffhanger jhela nahi jaa raha! ⏳🍿",
            "Ek emergency situation hai: ya toh tum zinda ho, ya fir mujhe detective hire karna padega! 🕵️‍♂️⚡",
            "Maine hamare baare me ek bohot bada revelation socha hai... reveal karu ya suspense me chhodu? ⏳",
        ]
    },
    "hindi": {
        "flirty": [
            "बातचीत थोड़ी थम सी गई है... सोचा आपको याद दिला दूँ कि आप याद आ रहे हैं 😉✨",
            "ख़ामोशी अच्छी है, पर आपकी बातों की रौनक कुछ और ही होती है 😊",
        ],
        "funny": [
            "क्या आप भी उन लोगों में से हैं जो मैसेज देखकर मन ही मन रिप्लाई दे देते हैं? 😂📱",
            "लगता है आपका फ़ोन हिमालय की गुफाओं में नेटवर्क ढूंढ रहा है! 😂🏔️",
        ],
        "respectful": [
            "नमस्ते! आशा है आपका काम अच्छा चल रहा होगा। जब भी फ़ुर्सत मिले, बताइएगा आप कैसे हैं। 😊",
            "हेलो! कोई जल्दबाज़ी नहीं, बस यह जानने के लिए मैसेज किया कि आपका दिन कैसा रहा। ✨",
        ],
        "casual": [
            "नमस्ते! आज कल किस चीज़ में व्यस्त हैं? ☕",
            "हेलो! हफ़्ते का कौन सा दिन सबसे ज़्यादा पसंद है आपको? ✨",
        ],
        "mysterious": [
            "ख़ामोशी भी बहुत कुछ कहती है... पर आपकी ख़ामोशी में कौन सा गहरा राज़ छुपा है? 🔮",
            "आपके बारे में एक ख़ास ख़्याल आया था, पर बताऊँगा सिर्फ़ आपके जवाब के बाद 🌙",
        ],
        "suspenseful": [
            "हमारी बातचीत ऐसे मोड़ पर रुकी है जैसे किसी थ्रिलर फ़िल्म का इंटरवल! ⏳🎬",
            "क्या आप किसी सीक्रेट मिशन पर हैं या सिर्फ़ फ़ोन से दूर? सच बताइएगा 🕵️‍♂️⏳",
        ]
    },
    "english": {
        "flirty": [
            "Our chat went quiet, but you’re still loud and clear on my mind 😉✨",
            "Did you get shy, or are you just playing hard to get? Either way, it’s working 😏",
            "Sending a little spark to reignite our chat 🔥 How’s your week treating you?",
        ],
        "funny": [
            "Are you being held hostage by your to-do list? Blink twice if you need rescue! 😂📋",
            "My psychic said our conversation would resume today... don’t let my psychic down! 🔮😂",
            "Did your phone fall into an alternate dimension, or did you just get caught in a 5-hour reel rabbit hole? 😂📱",
        ],
        "respectful": [
            "Hey! Just checking in. I know life gets super busy, so no worries at all—hope you're doing well! 😊",
            "Hi there! Saw something that made me think of our chat. Hope everything is going great with you! ✨",
        ],
        "casual": [
            "Reviving this chat because I refuse to let a good conversation fade out! How’s your week been? ☕",
            "Quick vibe check—how has the week been treating you so far? 🌟",
        ],
        "mysterious": [
            "Silence is the greatest mystery... but what is yours trying to tell me? 🔮",
            "You're playing hard to get or just unintentionally enigmatic? Either way, I'm hooked 🌙",
            "I had a fascinating thought about you today, but you have to unlock it first 🗝️✨",
        ],
        "suspenseful": [
            "Leaving this conversation on a cliffhanger should honestly be a punishable offense! ⏳😂",
            "I have one final question that will determine whether our story continues or ends here... 🕵️‍♂️⚡",
            "Are you testing my patience or is there an unexpected plot twist coming? ⏳",
        ]
    }
}


# ==============================================================================
# 2. GEMINI LLM CALLER (OPTIONAL HIGH-IQ AI LAYER)
# ==============================================================================

async def call_gemini_llm(prompt: str) -> Optional[str]:
    """
    Invokes Google Gemini via REST using GEMINI_API_KEY.
    Tries gemini-flash-lite-latest first, falls back to gemini-flash-latest.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip() or GEMINI_API_KEY
    if not api_key:
        return None

    models_to_try = ["gemini-flash-lite-latest", "gemini-flash-latest"]
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.85,
            "maxOutputTokens": 300,
            "topP": 0.95
        }
    }
    data_bytes = json.dumps(payload).encode("utf-8")

    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        try:
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                if resp.status == 200:
                    res_data = json.loads(resp.read().decode("utf-8"))
                    text = res_data["candidates"][0]["content"]["parts"][0]["text"]
                    return text.strip()
        except Exception as e:
            print(f"[AI_WINGMAN] Gemini {model_name} attempt skipped/failed: {e}")
            continue

    return None


# ==============================================================================
# 3. CORE PUBLIC SERVICES
# ==============================================================================

def normalize_interest(interest: str) -> str:
    """Strips emojis and converts to lowercase keyword."""
    s = interest.lower()
    for key in INTEREST_TOPIC_MAP:
        if key in s:
            return key
    return s.strip()

def extract_matched_topics(match_profile: Dict[str, Any]) -> List[str]:
    """Finds key topics like coffee, travel, pets, gym from match's profile."""
    topics = set()
    interests = match_profile.get("interests", []) or []
    for item in interests:
        norm = normalize_interest(str(item))
        if norm in INTEREST_TOPIC_MAP:
            topics.add(norm)

    bio = (match_profile.get("bio") or "").lower()
    for key in INTEREST_TOPIC_MAP:
        if key in bio:
            topics.add(key)

    prompts = match_profile.get("prompts", []) or []
    for p in prompts:
        ans = (p.get("answer") or "").lower()
        for key in INTEREST_TOPIC_MAP:
            if key in ans:
                topics.add(key)

    return list(topics)


VALID_TONES = ["mysterious", "suspenseful", "flirty", "funny", "respectful", "casual"]

TONE_DESCRIPTIONS = {
    "mysterious": "Deeply intriguing, enigmatic, and magnetic. Create an alluring curiosity gap that makes the user captivating and irresistible. Make them wonder.",
    "suspenseful": "High-tension cliffhanger, exciting mystery, thrilling secret or dilemma that compels an immediate reply.",
    "flirty": "Playful charm, charismatic romantic banter, subtle chemistry and tension.",
    "funny": "Hilarious wit, relatable comedy, banter that makes them laugh out loud.",
    "respectful": "Polite, thoughtful, high-value gentleman/lady approach.",
    "casual": "Chill, relaxed, low-pressure conversational curiosity."
}

async def generate_icebreakers(
    match_profile: Dict[str, Any],
    user_profile: Optional[Dict[str, Any]] = None,
    tone: str = "mysterious",
    language: str = "hinglish"
) -> Dict[str, Any]:
    """
    Generates 3-4 creative opening lines based on match's profile, interests, and bio.
    tone: 'mysterious' | 'suspenseful' | 'flirty' | 'funny' | 'respectful' | 'casual'
    language: 'hinglish' | 'hindi' | 'english'
    """
    tone = tone.lower() if tone in VALID_TONES else "mysterious"
    language = language.lower() if language in ["hinglish", "hindi", "english"] else "hinglish"

    match_name = match_profile.get("name", "Match")
    matched_topics = extract_matched_topics(match_profile)

    # 1. Try Gemini LLM if key is available
    api_key = os.getenv("GEMINI_API_KEY", "").strip() or GEMINI_API_KEY
    if api_key:
        tone_instruction = TONE_DESCRIPTIONS.get(tone, "")
        prompt = (
            f"You are Spark AI Wingman, the world's most charismatic, attractive, and witty dating assistant.\n"
            f"Generate 3 highly attractive, interesting, and magnetic opening lines for a dating app conversation.\n"
            f"Match's name: {match_name}\n"
            f"Match's bio: {match_profile.get('bio', '')}\n"
            f"Match's interests: {match_profile.get('interests', [])}\n"
            f"Tone: {tone.upper()} ({tone_instruction})\n"
            f"Language: {language} (use natural conversational phrasing, emojis where suitable).\n"
            f"CRITICAL REQUIREMENTS:\n"
            f"- Lines must be extremely attractive, clever, magnetic, and spark irresistible curiosity.\n"
            f"- No generic or boring lines! Give them an exciting reason to reply.\n"
            f"- If tone is MYSTERIOUS: create an intriguing curiosity gap that makes them eager to know more.\n"
            f"- If tone is SUSPENSEFUL: build high-stakes playful tension or a cliffhanger dilemma that demands an answer.\n"
            f"- Output strictly a valid JSON array of 3 strings: [\"line 1\", \"line 2\", \"line 3\"].\n"
            f"- No extra markdown or intro text."
        )
        llm_resp = await call_gemini_llm(prompt)
        if llm_resp:
            try:
                clean_json = llm_resp
                if "```json" in clean_json:
                    clean_json = clean_json.split("```json")[1].split("```")[0]
                elif "```" in clean_json:
                    clean_json = clean_json.split("```")[1].split("```")[0]
                parsed = json.loads(clean_json.strip())
                if isinstance(parsed, list) and len(parsed) >= 2:
                    return {
                        "suggestions": parsed[:4],
                        "matchedTopics": matched_topics,
                        "tone": tone,
                        "language": language,
                        "engine": "gemini-ai"
                    }
            except Exception:
                pass

    # 2. Local Smart Contextual Fallback Engine
    suggestions: List[str] = []

    # First add topic-specific openers if topics exist
    for topic in matched_topics:
        topic_dict = INTEREST_TOPIC_MAP.get(topic, {}).get(language, {}).get(tone, [])
        if topic_dict:
            suggestions.extend(random.sample(topic_dict, min(len(topic_dict), 2)))

    # Fill remaining from general openers
    general_pool = GENERAL_OPENERS.get(language, {}).get(tone, GENERAL_OPENERS["hinglish"]["mysterious"])
    available_general = [s for s in general_pool if s not in suggestions]
    random.shuffle(available_general)

    needed = 4 - len(suggestions)
    if needed > 0:
        suggestions.extend(available_general[:needed])

    # If still under 3, pull from fallback
    if len(suggestions) < 3:
        backup = GENERAL_OPENERS["hinglish"]["mysterious"]
        for b in backup:
            if b not in suggestions:
                suggestions.append(b)
            if len(suggestions) >= 3:
                break

    return {
        "suggestions": suggestions[:4],
        "matchedTopics": matched_topics,
        "tone": tone,
        "language": language,
        "engine": "smart-context"
    }


async def generate_chat_revivers(
    recent_messages: List[Dict[str, Any]],
    match_profile: Dict[str, Any],
    tone: str = "mysterious",
    language: str = "hinglish"
) -> Dict[str, Any]:
    """
    Generates follow-up lines when chat has stalled or went quiet.
    """
    tone = tone.lower() if tone in VALID_TONES else "mysterious"
    language = language.lower() if language in ["hinglish", "hindi", "english"] else "hinglish"

    match_name = match_profile.get("name", "Match")

    # 1. Try Gemini LLM if key is available
    api_key = os.getenv("GEMINI_API_KEY", "").strip() or GEMINI_API_KEY
    if api_key:
        last_msgs_text = "\n".join([f"{m.get('sender', 'user')}: {m.get('text', '')}" for m in recent_messages[-3:]])
        tone_instruction = TONE_DESCRIPTIONS.get(tone, "")
        prompt = (
            f"You are Spark AI Wingman, the ultimate charismatic dating assistant.\n"
            f"The conversation with {match_name} has stalled or gone quiet. Generate 3 magnetic, highly interesting follow-up messages to revive the chat.\n"
            f"Recent messages context:\n{last_msgs_text or 'No recent replies'}\n"
            f"Tone: {tone.upper()} ({tone_instruction})\n"
            f"Language: {language}\n"
            f"CRITICAL RULES:\n"
            f"- Do NOT sound needy, desperate, or annoyed. Sound confident, intriguing, and attractive.\n"
            f"- If tone is MYSTERIOUS or SUSPENSEFUL: create an irresistible hook, cliffhanger, or game they can't ignore.\n"
            f"- Output strictly a valid JSON array of 3 strings: [\"line 1\", \"line 2\", \"line 3\"].\n"
            f"- No extra markdown or intro text."
        )
        llm_resp = await call_gemini_llm(prompt)
        if llm_resp:
            try:
                clean_json = llm_resp
                if "```json" in clean_json:
                    clean_json = clean_json.split("```json")[1].split("```")[0]
                elif "```" in clean_json:
                    clean_json = clean_json.split("```")[1].split("```")[0]
                parsed = json.loads(clean_json.strip())
                if isinstance(parsed, list) and len(parsed) >= 2:
                    return {
                        "suggestions": parsed[:4],
                        "tone": tone,
                        "language": language,
                        "engine": "gemini-ai"
                    }
            except Exception:
                pass

    # 2. Local Smart Engine Pool
    pool = REVIVE_SUGGESTIONS.get(language, {}).get(tone, REVIVE_SUGGESTIONS["hinglish"]["mysterious"])
    sampled = random.sample(pool, min(len(pool), 4))
    return {
        "suggestions": sampled,
        "tone": tone,
        "language": language,
        "engine": "smart-context"
    }


def generate_profile_coach(
    user_profile: Dict[str, Any],
    language: str = "hinglish"
) -> Dict[str, Any]:
    """
    Analyzes user profile and returns a Strength Score (0-100) along with
    actionable tips to boost matches by 3x.
    """
    language = language.lower() if language in ["hinglish", "hindi", "english"] else "hinglish"

    photos = user_profile.get("photos", []) or []
    bio = user_profile.get("bio", "") or ""
    interests = user_profile.get("interests", []) or []
    prompts = user_profile.get("prompts", []) or []
    occupation = user_profile.get("occupation", "") or ""
    education = user_profile.get("education", "") or ""
    relationship_goals = user_profile.get("relationship_goals", "") or ""

    score = 0
    tips = []

    # 1. Photos Analysis (Max 40 pts)
    photo_count = len(photos)
    if photo_count >= 4:
        score += 40
    elif photo_count >= 2:
        score += 25
        if language == "hinglish":
            tips.append({
                "tag": "📸 Photos",
                "title": "2 Aur Photos Add Karo",
                "desc": "Kam se kam 4 photos rakhne se matches 2.5x badh jaate hain. Ek smiling outdoor photo add karo!"
            })
        elif language == "hindi":
            tips.append({
                "tag": "📸 फ़ोटो",
                "title": "2 और तस्वीरें जोड़ें",
                "desc": "कम से कम 4 फ़ोटो रखने से प्रोफ़ाइल को 2.5 गुना ज़्यादा लाइक्स मिलते हैं।"
            })
        else:
            tips.append({
                "tag": "📸 Photos",
                "title": "Add 2 More Photos",
                "desc": "Profiles with at least 4 photos get 2.5x more matches. Include an outdoor full-body shot!"
            })
    else:
        score += 10
        if language == "hinglish":
            tips.append({
                "tag": "🚨 Photos",
                "title": "Photos Upload Karo",
                "desc": "Ek photo se profiles par trust kam hota hai. Apni best 3-4 candid photos upload karo."
            })
        elif language == "hindi":
            tips.append({
                "tag": "🚨 फ़ोटो",
                "title": "और तस्वीरें अपलोड करें",
                "desc": "सिर्फ़ एक फ़ोटो से मैच मिलने की संभावना कम हो जाती है। अपनी 3-4 बेहतरीन फ़ोटो जोड़ें।"
            })
        else:
            tips.append({
                "tag": "🚨 Photos",
                "title": "Upload More Photos",
                "desc": "Single-photo profiles get 70% fewer matches. Add at least 3 high-quality portraits."
            })

    # 2. Bio Analysis (Max 25 pts)
    bio_words = len(bio.strip().split())
    if bio_words >= 15:
        score += 25
    elif bio_words >= 5:
        score += 15
        if language == "hinglish":
            tips.append({
                "tag": "✍️ Bio",
                "title": "Bio Me Thodi Detail Badhao",
                "desc": "Tumhe kya pasand hai aur weekend pe kya karte ho, yeh bio me add karo taaki log easily conversation start kar sakein."
            })
        elif language == "hindi":
            tips.append({
                "tag": "✍️ बायो",
                "title": "बायो को थोड़ा और आकर्षक बनाएं",
                "desc": "अपने शौक़ और वीकेंड के बारे में 2 लाइनें लिखें ताकि लोग आसानी से बात शुरू कर सकें।"
            })
        else:
            tips.append({
                "tag": "✍️ Bio",
                "title": "Add More Character to Bio",
                "desc": "Tell people what you nerd out on or what a typical Sunday looks like. Give them conversation bait!"
            })
    else:
        score += 5
        if language == "hinglish":
            tips.append({
                "tag": "✍️ Bio",
                "title": "Ek Engaging Bio Likho",
                "desc": "Khali bio se log swipe left kar dete hain. 2 witty lines likho apni personality ke baare me!"
            })
        elif language == "hindi":
            tips.append({
                "tag": "✍️ बायो",
                "title": "एक बढ़िया बायो लिखें",
                "desc": "खाली बायो से लोग आगे बढ़ जाते हैं। अपने व्यक्तित्व के बारे में 2 मज़ेदार लाइनें जोड़ें।"
            })
        else:
            tips.append({
                "tag": "✍️ Bio",
                "title": "Write an Engaging Bio",
                "desc": "A witty 2-line bio increases right-swipes by 60%. Share your vibe!"
            })

    # 3. Interests Analysis (Max 15 pts)
    if len(interests) >= 5:
        score += 15
    elif len(interests) >= 3:
        score += 10
    else:
        score += 5
        if language == "hinglish":
            tips.append({
                "tag": "🎯 Interests",
                "title": "5 Interests Select Karo",
                "desc": "Coffee, Travel, Music jaise 5 tags select karne se matching algorithm tumhare jaise vibes walo se connect karta hai."
            })
        elif language == "hindi":
            tips.append({
                "tag": "🎯 रुचियां",
                "title": "कम से कम 5 रुचियां चुनें",
                "desc": "कॉफ़ी, म्यूज़िक या ट्रैवल जैसे टैग जोड़ने से सही मैच ढूंढने में मदद मिलती है।"
            })
        else:
            tips.append({
                "tag": "🎯 Interests",
                "title": "Pick at least 5 Interests",
                "desc": "Selecting tags like Coffee, Travel, or Music helps our matchmaker find like-minded people."
            })

    # 4. Profile Prompts (Max 10 pts)
    if len(prompts) >= 2:
        score += 10
    elif len(prompts) == 1:
        score += 6
        if language == "hinglish":
            tips.append({
                "tag": "💡 Prompts",
                "title": "1 Aur Prompt Add Karo",
                "desc": "Prompts conversation ke sabse badhiya icebreakers hote hain. Ek funny prompt answer add karo!"
            })
        elif language == "hindi":
            tips.append({
                "tag": "💡 प्रॉमप्ट्स",
                "title": "1 और सवाल का जवाब जोड़ें",
                "desc": "प्रॉमप्ट्स बातचीत शुरू करने का सबसे आसान ज़रिया होते हैं।"
            })
        else:
            tips.append({
                "tag": "💡 Prompts",
                "title": "Add 1 More Prompt",
                "desc": "Prompts are the #1 conversation starter. Add one witty answer to spark chats!"
            })
    else:
        score += 2
        if language == "hinglish":
            tips.append({
                "tag": "💡 Prompts",
                "title": "Spark Prompts Add Karo",
                "desc": "Prompts add karne se samne wale ko pehla message bhejna 10x aasan lagta hai."
            })
        elif language == "hindi":
            tips.append({
                "tag": "💡 प्रॉमप्ट्स",
                "title": "प्रोफ़ाइल प्रॉमप्ट जोड़ें",
                "desc": "प्रॉमप्ट जोड़ने से सामने वाले के लिए बातचीत शुरू करना बहुत आसान हो जाता है।"
            })
        else:
            tips.append({
                "tag": "💡 Prompts",
                "title": "Add Profile Prompts",
                "desc": "Profiles with prompts receive 4x more first messages. Pick a prompt to show your sense of humor!"
            })

    # 5. Career & Relationship Goals (Max 10 pts)
    if occupation and relationship_goals:
        score += 10
    elif occupation or relationship_goals:
        score += 5
    else:
        if language == "hinglish":
            tips.append({
                "tag": "💼 Career & Goals",
                "title": "Job Aur Relationship Goal Set Karo",
                "desc": "Yeh batane se ki tum kya chahte ho (Long-term, Casual) genuine matches jaldi aate hain."
            })
        elif language == "hindi":
            tips.append({
                "tag": "💼 लक्ष्य",
                "title": "अपना काम और रिलेशनशिप गोल जोड़ें",
                "desc": "यह स्पष्ट करने से कि आप क्या ढूंढ रहे हैं, सही लोग आकर्षित होते हैं।"
            })
        else:
            tips.append({
                "tag": "💼 Goals",
                "title": "Set Relationship Intentions",
                "desc": "Being clear about what you're looking for attracts genuine and compatible people."
            })

    # Summary praise based on score
    if score >= 85:
        summary = "Tumhari profile super attractive hai! ✨ Minor tweaks se conversion aur badh sakti hai." if language == "hinglish" else ("आपकी प्रोफ़ाइल बहुत शानदार है! ✨" if language == "hindi" else "Your profile looks stellar! ✨ Ready to turn heads.")
    elif score >= 60:
        summary = "Solid profile! In 2-3 tips ko follow karke match rate 2x boost ho sakta hai 🚀" if language == "hinglish" else ("अच्छी प्रोफ़ाइल है! इन सुझावों से मैच रेट दोगुना हो सकता है 🚀" if language == "hindi" else "Solid profile! These quick tweaks can easily 2x your match rate 🚀")
    else:
        summary = "Bas thoda polish baaki hai! In tips se tumhari profile Spark par stand out karegi ⚡" if language == "hinglish" else ("बस थोड़ा सुधार बाक़ी है! इन सुझावों से आपकी प्रोफ़ाइल चमक उठेगी ⚡" if language == "hindi" else "A little polish will make a huge difference! Follow these tips to stand out ⚡")

    return {
        "score": min(score, 100),
        "summary": summary,
        "tips": tips[:4],
        "metrics": {
            "photosCount": photo_count,
            "bioLength": bio_words,
            "interestsCount": len(interests),
            "promptsCount": len(prompts)
        }
    }
