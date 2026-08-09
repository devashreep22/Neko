import { motion } from "framer-motion";
import catImage from "../assets/cat.png";

function Pet() {
    return (
        <motion.img
            src={catImage}
            alt="Neko AI Cat"
            animate={{
                scale: [1, 1.03, 1],
            }}
            transition={{
                duration: 2.5,
                repeat: Infinity,
                ease: "easeInOut",
            }}
            style={{
                width: "180px",
                userSelect: "none",
                pointerEvents: "none",
            }}
        />
    );
}

export default Pet;