namespace PLO8;
using System;
using System.Collections.Generic;
using System.Runtime.ExceptionServices;
using Microsoft.VisualBasic;

public class PLO8
{
    public static void Main()
    {
        // Ctrl + / to un/comment blocks of lines
        Deck deck = new Deck();
        Console.Write("\nFilling shoe...");
        int numberOfDecks = 1;
        deck.FillDeck(numberOfDecks); // Fill the deck with 8 decks of cards
        deck.PrintDeck();
        Console.WriteLine("\nShuffling shoe\n");
        deck.ShuffleDeck();
        //deck.InsertCutCard();
        //deck.Deal(numberOfDecks * 13); // Deal enough hands to reach cut card
        //deck.PrintDeck();
        //Console.WriteLine(deck.cards.Count);
        //deck.CheckAllRules(false);
    }
}

public class Card
{
    public enum Suits
    {
        Spades, Diamonds, Clubs, Hearts
    }

    public int Value
    {
        get;
        set;
    }

    public Suits Suit
    {
        get;
        set;
    }

    public int DeckNumber
    {
        get;
        set;
    }

    //Used to get full name, also useful if you want to just get the named value
    public string NamedValue
    {
        get
        {
            string name = string.Empty;
            switch (Value)
            {
                case (14):
                    name = "Ace";
                    break;
                case (13):
                    name = "King";
                    break;
                case (12):
                    name = "Queen";
                    break;
                case (11):
                    name = "Jack";
                    break;
                default:
                    name = Value.ToString();
                    break;
            }

            return name;
        }
    }

    public string Name
    {
        get
        {
            return NamedValue + " of " + Suit.ToString() + ", deck number " + DeckNumber;
        }
    }

    public Card(int Value, Suits Suit, int DeckNumber = 1)
    {
        this.Value = Value;
        this.Suit = Suit;
        this.DeckNumber = DeckNumber;
    }
    public Card()
    { }
}


public class Deck
{
    public List<Card> cards = new List<Card>();
    private Random rng = new Random();
    private List<Card> playerCards = new List<Card>();
    private List<Card> bankerCards = new List<Card>();
    // private bool playerThirdCardExists = false;
    // private bool bankerThirdCardExists = false;
    // private string listOfWinners = "";
    public void FillDeck(int NumberofDecks)
    {
        int totalCards = NumberofDecks * 52;
        //Can use a single loop utilising the mod operator % and Math.Floor
        //Using division based on 13 cards in a suit
        for (int i = 0; i < totalCards; i++)
        {
            Card.Suits suit = (Card.Suits)(Math.Floor((decimal)i / 13) % 4);
            //Add 2 to value as a cards start at 2
            int val = i % 13 + 2;
            int deckNumber = (int)Math.Floor((decimal)i / 52) + 1; // Calculate the deck number
            cards.Add(new Card(val, suit, deckNumber));
        }
    }

    public void PrintDeck()
    {
        foreach (Card card in this.cards)
        {
            Console.WriteLine(card.Name);
        }
    }

    public void ShuffleDeck()
    {   //fisher-yates shuffle https://en.wikipedia.org/wiki/Fisher%E2%80%93Yates_shuffle
        for (int i = this.cards.Count - 1; i > 0; i--)
        {
            int j = rng.Next(0, i + 1);
            (this.cards[i], this.cards[j]) = (this.cards[j], this.cards[i]);
        }
        //listOfWinners = ""; //reset list of winners
    }

    public void Deal(int i)
    {
        while (i > 0)
        {
            playerCards.Clear();
            bankerCards.Clear();
            // playerThirdCardExists = false;
            // Deal two cards to each player
            Console.WriteLine("\n\nDealing cards...");
            playerCards.Add(Draw());
            Console.WriteLine($"Player receives: {playerCards[0].Name}");

            playerCards.Add(Draw());
            Console.WriteLine($"Player receives: {playerCards[1].Name}");

            bankerCards.Add(Draw());
            Console.WriteLine($"\nBanker receives: {bankerCards[0].Name}");

            bankerCards.Add(Draw());
            Console.WriteLine($"Banker receives: {bankerCards[1].Name}");
            i--;
        }
    }
    public Card Draw()
    {
        // CheckCutCard();
        Card card = this.cards[this.cards.Count - 1];
        this.cards.RemoveAt(this.cards.Count - 1);
        return card;
    }
    // public void DetemineWinnerAndSave(ref string listOfWinners)
    // {

    //     if (PlayerTotalBaccaratValue() > BankerTotalBaccaratValue())
    //     {
    //         Console.WriteLine("\nPlayer wins!");
    //         listOfWinners += "P";
    //     }
    //     else if (PlayerTotalBaccaratValue() < BankerTotalBaccaratValue())
    //     {
    //         Console.WriteLine("\nBanker wins!");
    //         listOfWinners += "B";
    //     }
    //     else
    //     {
    //         Console.WriteLine("\nIt's a tie!");
    //         listOfWinners += "T";
    //     }
    // }

    public void ExportToCSV()
    {
        using (StreamWriter sw = new StreamWriter("results.txt", false))
        {
            //sw.WriteLine(listOfWinners);
        }
        Console.WriteLine("File exported!");
    }
}