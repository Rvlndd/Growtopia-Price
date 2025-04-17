import { checkItemPrice } from './price.js';

(async () => {
    try {
        const data = await checkItemPrice("MAGPLANT 5000");
        console.log(data);
    } catch (err) {
        console.error("fail:", err.message);
    }
})();
