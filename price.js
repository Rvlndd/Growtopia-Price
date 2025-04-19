import axios from 'axios';
import * as fuzz from 'fuzzball'; // this library name is 100% inspired by the dev penis 
import { GoogleGenerativeAI } from "@google/generative-ai";
import dotenv from 'dotenv';
import { z } from 'zod'; 

dotenv.config();

const disSearchUrl = "https://discord.com/api/v9/guilds/571992648190263317/messages/search";
const disHeaders = {
    "Authorization": process.env.DISCORD_AUTHORIZATION,
    "Cookie": "__dcfduid=5beb9ea0b7d511efa06c211b7d074ae8; __sdcfduid=5beb9ea1b7d511efa06c211b7d074ae83f6ccdce918fdc171e548a2f463be0793d5e39354e1615876ad75f9c103dc74c", // this feels illegal but ok
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36" // totally a real browser trust
};

const genAI = new GoogleGenerativeAI(process.env.GENAI_API_KEY || '');

const geminiModel = genAI.getGenerativeModel({
    model: "gemini-2.0-flash",
    systemInstruction: `
You are an AI specialized in determining the price of items based on user-provided data.

#### **Pricing Rules:**
1. **Currency Conversion:**
   - If a price is given **without** a currency name, assume it is in WL (World Locks).
   - **100 WL = 100 DL = 1 BGL.**
2. **Response Format:**
   - You must **only** respond with a JSON object.
   - The JSON should follow one of two formats based on the item's pricing type:
     - \`"type": "each"\` → For individually priced items.
     - \`"type": "per"\` → For items sold in bulk (e.g., 5/1, 90/1).

---

### **JSON Response Format**

#### **For "each" Items (Individually Priced)**
\`\`\`json
{
  "Item_Name": "<item name>",
  "item_price": <average price in WL>,
  "priceindl": "<formatted price in BGL/DL/WL>",
  "type": "each"
}
\`\`\`
 **Example Calculation:**
If the given prices are **1 BGL, 50 DL, and 2 WL**:
- Convert everything to WL: **(1 BGL = 10000 WL, 50 DL = 5000 WL, 2 WL = 2 WL)**
- Total price: **15002 WL**
- Formatted \`"priceindl"\`: \`"1 BGL 50 DL 2 WL"\`

\`\`\`json
{
  "Item_Name": "Legendary Wings",
  "item_price": 15002,
  "priceindl": "1 BGL 50 DL 2 WL",
  "type": "each"
}
\`\`\`

---

#### **For "per" Items (Bulk Pricing)**
\`\`\`json
{
  "Item_Name": "<item name>",
  "item_price": <amount per WL>,
  "type": "per"
}
\`\`\`
 **Example Calculation:**
If the price is **90/1**, the \`"item_price"\` is **90** (meaning 90 items per WL).

\`\`\`json
{
  "Item_Name": "Ruby Block",
  "item_price": 90,
  "type": "per"
}
\`\`\`
**‼ Important:** \`"priceindl"\` should **not** be included for "per" items.

---

### **Additional Rules:**
1. **Price Filtering:** Ignore unreasonable prices that are **significantly higher or lower** than the average to prevent manipulation.
2. **Item Name Handling:**
   - Extract the **exact** item name from the input (\`itnm\` field).
   - Ignore any unnecessary words or formatting.
3. **Data Source:**
   - The input is sourced from **Discord search results**.
    `
});

const normalizeString = (s) => {
    return s.replace(/[^a-zA-Z0-9\s]/g, "").toLowerCase();
};

const searchFuzzy = (itemName, line, threshold = 80) => {
    const normalizedItem = normalizeString(itemName);
    const normalizedLine = normalizeString(line);
    return fuzz.partial_ratio(normalizedItem, normalizedLine) >= threshold;
};

const formatPrice = (wlPrice) => {
    let priceNum = typeof wlPrice === 'string' ? parseInt(wlPrice, 10) : wlPrice;

    if (isNaN(priceNum)) {
        console.error("bro that price is not a number:", wlPrice);
        return "Invalid Price"; 
    }
    priceNum = Math.floor(priceNum); 

    const bgl = Math.floor(priceNum / 10000);
    const remaining = priceNum % 10000;
    const dl = Math.floor(remaining / 100);
    const wl = remaining % 100;

    const formatCurr = [];

    if (bgl > 0) formatCurr.push(`${bgl} BGL`);
    if (dl > 0) formatCurr.push(`${dl} DL`);
    if (wl > 0) formatCurr.push(`${wl} WL`);

    if (formatCurr.length === 0) return "0 WL";

    return formatCurr.join(" ");
};

const PriceResponseSchema = z.object({
    Item_Name: z.string(),
    item_price: z.number(),
    priceindl: z.string().optional().nullable(), 
    type: z.enum(["each", "per"]),
});

export async function checkItemPrice(itemName) {
    if (!itemName) {
        throw new Error("bro send item name????");
    }

    console.log(`searchin for: ${itemName}`);

    try {
        const discordParams = { content: itemName };
        const discordRes = await axios.get(disSearchUrl, {
            headers: disHeaders,
            params: discordParams,
        });

        if (discordRes.status !== 200) {
            console.error("discord api hate us:", discordRes.status, discordRes.data);
            throw new Error("discord search failed lol");
        }

        const data = discordRes.data;

        const filteredResults = new Set();
        const priceRegex = /(\d+(?:[\.,]\d+)?(?:k|m|b)?\s*(?:wl|dl|bgl)?)|(\d+\/\d+)/i;

        for (const messageGroup of data?.messages || []) {
            if (messageGroup && messageGroup.length > 0) {
                const content = messageGroup[0]?.content;
                if (!content) continue; 

                const lines = content.split('\n');
                for (const line of lines) {
                    if (priceRegex.test(line) && searchFuzzy(itemName, line, 80)) {
                        filteredResults.add(line.trim()); 
                    }
                }
            }
        }

        if (filteredResults.size === 0) {
            console.log("no relevant messages found for:", itemName);
            throw new Error("couldnt find shit about that item boss");
        }

        const aiPrompt = `itnm: ${itemName}\n` + [...filteredResults].join("\n");

        const aiResult = await geminiModel.generateContent(aiPrompt);
        const aiResponseText = aiResult.response.text();

        const cleanedJsonText = aiResponseText.replace(/^```json\s*|```$/g, "").trim();
        let priceData;
        try {
            const parsedJson = JSON.parse(cleanedJsonText);
            priceData = PriceResponseSchema.parse(parsedJson);

        } catch (e) {
            console.error("ai returned garbage or json broke:", e);
            console.error("raw ai text:", aiResponseText);
            throw new Error("ai response was weird af");
        }

        if (priceData.type === "each" && priceData.item_price != null) {
            priceData.priceindl = formatPrice(priceData.item_price);
        } else {
            priceData.priceindl = null;
        }

        return priceData;

    } catch (error) {
        console.error(error);
        throw error;
    }
}
